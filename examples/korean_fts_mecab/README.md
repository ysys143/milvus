# Korean full-text search in Milvus with MeCab-grade tokenization

Two working ways to attach a **custom CJK (Korean) tokenizer** to Milvus full-text
search — the Milvus counterpart to wiring MeCab into PostgreSQL the way the
[`ysys143/textsearch`](https://github.com/ysys143/textsearch) benchmark does with the
`textsearch_ko` extension.

That benchmark's headline finding is the motivation for this whole directory:

> **The tokenizer determines ~80% of Korean BM25 quality.** Morphological analyzers
> (MeCab / nori) reach NDCG ≈ 0.61–0.64 on MIRACL-ko BM25; naïve tokenization
> collapses. It also documents that Vespa's Korean support *failed* because Lucene
> Nori (Java) could not be pushed into the C++ content node.

Milvus sidesteps that language-boundary problem two different ways, both configured
purely through the collection's analyzer params — **no Milvus rebuild**.

| | Approach 1: built-in `lindera` | Approach 2: external `grpc` |
|---|---|---|
| Engine | pure-Rust reimpl of MeCab, **same `mecab-ko-dic`** | **real libmecab (mecab-ko)** in a sidecar |
| PostgreSQL analogue | linking a mecab-dict-based parser in-process | `textsearch_ko` linking libmecab, but decoupled via RPC |
| Extra process | none | the MeCab gRPC server |
| Rebuild Milvus | no | no |
| Best when | you want MeCab-grade Korean with zero ops | you need *your* exact mecab-ko / user dict / tuning |
| Example | [`01_lindera_kodic.py`](01_lindera_kodic.py) | [`02_grpc_mecab.py`](02_grpc_mecab.py) + [`mecab_grpc_server/`](mecab_grpc_server/) |

## Why these two exist in Milvus

Tokenizer selection lives in one place in the tantivy binding
(`internal/core/thirdparty/tantivy/tantivy-binding/src/analyzer/tokenizers/tokenizer.rs`,
`get_builder_with_tokenizer`). The Go layer
(`internal/util/analyzer/canalyzer`) does **not** hard-code a tokenizer whitelist —
it forwards analyzer JSON straight to Rust — so `lindera` and `grpc` are the two
supported extension points for CJK, and both are reachable from schema config alone.

- `lindera` `ko-dic` builds the actual `mecab-ko-dic-2.1.1-20180720` dictionary
  (`.../analyzer/dict/lindera/ko_dic.rs`), so its segmentation units match mecab-ko.
- `grpc` delegates tokenization over `/milvus.proto.tokenizer.Tokenizer/Tokenize`
  (`.../analyzer/tokenizers/grpc_tokenizer.rs`), which is what lets a real libmecab
  server plug in.

## Approach 1 — built-in lindera + ko-dic

```python
analyzer_params = {
    "tokenizer": {
        "type": "lindera",
        "dict_kind": "ko-dic",
        "filter": [{"kind": "korean_stop_tags",
                    "tags": ["JKS","JKB","EP","EF","EC", ...]}],  # drop particles/endings
    },
    "filter": ["lowercase"],
}
```

Run: `python 01_lindera_kodic.py` (needs `pymilvus>=2.5` and a running Milvus).
On first use Milvus downloads + builds ko-dic into its dict cache.

The `korean_stop_tags` filter reproduces the content-word filtering `textsearch_ko`
does: `무궁화꽃이 피었습니다` → `무궁화 / 꽃 / 피`. It also supports a user dictionary
(`"user_dict": {"type": "local", "path": "user.csv"}`) using the same CSV format as
a MeCab user dictionary, so existing dictionary assets carry over.

## Approach 2 — external gRPC MeCab

When you must run *your* libmecab (custom build, user dictionary, specific tagset
behavior), run the reference server in [`mecab_grpc_server/`](mecab_grpc_server/)
and point the analyzer at it:

```python
analyzer_params = {"tokenizer": {"type": "grpc", "endpoint": "http://mecab-tokenizer:50051"}}
```

The tricky part — recovering **byte offsets** from MeCab surface forms — is
implemented and unit-tested in `mecab_grpc_server/mecab_analyze.py`. See that
directory's README for the contract, Docker build, and production notes.

## Choosing

- **Just want strong Korean BM25 with minimal ops** → Approach 1. Same dictionary,
  no extra service.
- **Must reproduce a specific mecab-ko setup / user dict / tuning** → Approach 2.
- **Need in-process real libmecab specifically** → not covered here; that would mean
  adding a libmecab-FFI Rust tokenizer to the tantivy binding and registering it in
  `get_builder_with_tokenizer` — the highest-effort option (Milvus core rebuild),
  and usually unnecessary given Approaches 1 and 2.

## Verifying

```bash
# offset / POS logic (no Milvus, no MeCab, no network):
cd mecab_grpc_server && python -m unittest test_mecab_analyze -v
```

The pymilvus scripts additionally require a running Milvus; Approach 2 also requires
the MeCab gRPC server reachable from the Milvus process.
