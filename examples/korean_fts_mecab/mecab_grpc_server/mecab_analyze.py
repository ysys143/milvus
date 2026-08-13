"""Pure tokenization / byte-offset / POS-filter logic for the MeCab gRPC tokenizer.

This module is intentionally free of any ``grpc`` or ``MeCab`` import so it can be
unit-tested anywhere (see ``test_mecab_analyze.py``). The morphological analyzer is
injected as a ``Tagger``: production wires in :class:`MeCabTagger` (libmecab through
the ``mecab-python3`` / ``mecab-ko`` binding), tests wire in a fake tagger with a
fixed morpheme list.

Why this file exists
--------------------
Milvus' gRPC tokenizer contract requires each returned token to carry **byte**
offsets into the original UTF-8 text (``offset_from`` / ``offset_to``). MeCab only
hands back surface forms and POS tags -- it does not give byte spans that line up
with the original string once whitespace is involved. Recovering correct byte
offsets is the part that is easy to get subtly wrong (char index vs. byte index on
multi-byte Hangul/Han), so it lives here in one small, tested function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


# mecab-ko-dic tagset: tags dropped by default for Korean BM25. Mirrors the
# filtering textsearch_ko applies (particles / endings / symbols) so that only
# content morphemes reach the inverted index. Override per-request via the
# gRPC "stop_pos" / "keep_pos" parameters, or per-deployment via the server flags.
DEFAULT_STOP_POS = frozenset(
    {
        # 조사 (particles)
        "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",
        # 어미 (endings)
        "EP", "EF", "EC", "ETN", "ETM",
        # 접미사 (suffixes) -- optional; comment out to keep derivational suffixes
        "XSN", "XSV", "XSA",
        # 기호 (symbols / punctuation)
        "SF", "SE", "SSO", "SSC", "SC", "SY",
    }
)


@dataclass(frozen=True)
class Morph:
    """A morpheme as produced by a morphological analyzer."""

    surface: str
    pos: str  # mecab-ko-dic part-of-speech tag, e.g. "NNG", "JKS", "VV"


@dataclass(frozen=True)
class Tok:
    """A token in the shape Milvus' gRPC tokenizer expects.

    ``offset_from`` / ``offset_to`` are **byte** offsets into the UTF-8 encoding of
    the original text; ``offset_to`` is exclusive.
    """

    text: str
    offset_from: int
    offset_to: int
    position: int
    position_length: int = 1


def _byte_len(s: str) -> int:
    return len(s.encode("utf-8"))


def tokenize(
    text: str,
    morphs: Sequence[Morph],
    stop_pos: frozenset = DEFAULT_STOP_POS,
    lowercase: bool = True,
) -> List[Tok]:
    """Turn an ordered morpheme list into Milvus tokens with correct byte offsets.

    Morphemes must be in surface order (as MeCab emits them). Each surface is
    located in ``text`` at or after a running cursor -- MeCab surfaces are verbatim
    substrings of the input, so a forward search is exact and also naturally skips
    the whitespace MeCab drops between tokens.

    Dropped morphemes (``pos in stop_pos``) still advance the cursor -- they consume
    their span of the original text -- but do not occupy a ``position``. Positions
    are therefore contiguous over *emitted* tokens, which is what BM25 / phrase
    matching expects.
    """
    tokens: List[Tok] = []
    char_cursor = 0
    byte_cursor = 0  # byte offset that corresponds to char_cursor
    position = 0

    for m in morphs:
        surface = m.surface
        if not surface:
            continue

        idx = text.find(surface, char_cursor)
        if idx == -1:
            # Surface is not a verbatim substring from the cursor onward (rare:
            # would require MeCab to normalize the surface). Best-effort: assume it
            # sits at the cursor so char/byte cursors stay in sync for the rest.
            idx = char_cursor

        start_byte = byte_cursor + _byte_len(text[char_cursor:idx])
        end_byte = start_byte + _byte_len(surface)
        # advance both cursors together to keep them consistent
        char_cursor = idx + len(surface)
        byte_cursor = end_byte

        if m.pos in stop_pos:
            continue

        out_text = surface.lower() if lowercase else surface
        tokens.append(Tok(out_text, start_byte, end_byte, position))
        position += 1

    return tokens
