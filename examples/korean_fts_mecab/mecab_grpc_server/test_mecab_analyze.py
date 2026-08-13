"""Unit tests for the byte-offset / POS-filter logic.

Runs with plain ``python -m unittest`` (or ``python test_mecab_analyze.py``) -- no
MeCab, no grpc, no network. A fake tagger supplies a fixed morpheme list so the
offset arithmetic is checked deterministically.

The key invariant under test: for every emitted token,
``original_utf8_bytes[offset_from:offset_to]`` decodes back to the token's surface
form (before lowercasing). If this holds, Milvus highlighting and phrase-match slop
line up with the source text.
"""

import unittest

from mecab_analyze import DEFAULT_STOP_POS, Morph, tokenize


def _decode(text: str, tok) -> str:
    return text.encode("utf-8")[tok.offset_from : tok.offset_to].decode("utf-8")


class TestTokenize(unittest.TestCase):
    def test_korean_pos_filtering_and_offsets(self):
        # The textsearch_ko reference reduces "무궁화꽃이 피었습니다" to the content
        # morphemes 무궁화 / 꽃 / 피. Reproduce that here.
        text = "무궁화꽃이 피었습니다"
        morphs = [
            Morph("무궁화", "NNG"),
            Morph("꽃", "NNG"),
            Morph("이", "JKS"),   # particle -> dropped
            Morph("피", "VV"),
            Morph("었", "EP"),    # ending -> dropped
            Morph("습니다", "EF"),  # ending -> dropped
        ]
        toks = tokenize(text, morphs)

        self.assertEqual([t.text for t in toks], ["무궁화", "꽃", "피"])
        # contiguous positions over emitted tokens
        self.assertEqual([t.position for t in toks], [0, 1, 2])
        # exact byte spans (each Hangul syllable is 3 UTF-8 bytes)
        self.assertEqual((toks[0].offset_from, toks[0].offset_to), (0, 9))   # 무궁화
        self.assertEqual((toks[1].offset_from, toks[1].offset_to), (9, 12))  # 꽃
        self.assertEqual((toks[2].offset_from, toks[2].offset_to), (16, 19)) # 피 (after the space)
        # offsets round-trip back to the surface for every token
        for t, expected in zip(toks, ["무궁화", "꽃", "피"]):
            self.assertEqual(_decode(text, t), expected)

    def test_mixed_ascii_and_hangul_offsets(self):
        text = "Milvus 벡터 DB"
        morphs = [
            Morph("Milvus", "SL"),  # foreign word
            Morph("벡터", "NNG"),
            Morph("DB", "SL"),
        ]
        toks = tokenize(text, morphs)
        self.assertEqual([t.text for t in toks], ["milvus", "벡터", "db"])  # lowercased
        # byte spans still refer to the ORIGINAL (non-lowercased) text
        self.assertEqual(_decode(text, toks[0]), "Milvus")   # bytes 0..6
        self.assertEqual((toks[0].offset_from, toks[0].offset_to), (0, 6))
        self.assertEqual(_decode(text, toks[1]), "벡터")      # bytes 7..13
        self.assertEqual((toks[1].offset_from, toks[1].offset_to), (7, 13))
        self.assertEqual(_decode(text, toks[2]), "DB")        # bytes 14..16
        self.assertEqual((toks[2].offset_from, toks[2].offset_to), (14, 16))

    def test_lowercase_disabled_preserves_surface(self):
        text = "ABC"
        toks = tokenize(text, [Morph("ABC", "SL")], lowercase=False)
        self.assertEqual(toks[0].text, "ABC")

    def test_repeated_surface_advances_cursor(self):
        # The same surface twice must map to two distinct spans, not the first one
        # both times (the forward search from a running cursor guarantees this).
        text = "가 나 가"
        morphs = [Morph("가", "NNG"), Morph("나", "NNG"), Morph("가", "NNG")]
        toks = tokenize(text, morphs)
        # the two 가 morphemes must land on the first and last spans, not both on
        # the first occurrence
        self.assertEqual((toks[0].offset_from, toks[0].offset_to), (0, 3))   # 가
        self.assertEqual((toks[1].offset_from, toks[1].offset_to), (4, 7))   # 나
        self.assertEqual((toks[2].offset_from, toks[2].offset_to), (8, 11))  # 가
        for t, expected in zip(toks, ["가", "나", "가"]):
            self.assertEqual(_decode(text, t), expected)

    def test_all_default_stop_pos_are_dropped(self):
        text = "책"
        morphs = [Morph("책", "NNG")] + [Morph("x", pos) for pos in DEFAULT_STOP_POS]
        toks = tokenize(text, morphs)
        self.assertEqual([t.text for t in toks], ["책"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
