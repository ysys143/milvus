# MeCab gRPC tokenizer for Milvus

A reference implementation of Milvus' **external gRPC tokenizer** contract, backed
by **MeCab (mecab-ko)**. Milvus calls this service to tokenize each document field
and each query string; you get real libmecab morphological analysis without
rebuilding Milvus.

```
Milvus (tantivy grpc tokenizer)  --gRPC-->  this server  --libmecab-->  morphemes
        analyzer config                       server.py                 mecab-ko-dic
```

## Files

| File | Purpose |
|------|---------|
| `tokenizer.proto`       | The contract Milvus speaks (`/milvus.proto.tokenizer.Tokenizer/Tokenize`). Mirrors milvus-proto. |
| `mecab_analyze.py`      | Pure logic: surface → **byte offsets** + POS filtering. No grpc/mecab imports. |
| `test_mecab_analyze.py` | Unit tests for the offset math (`python -m unittest test_mecab_analyze`). No deps. |
| `server.py`             | libmecab binding (`MeCabTagger`) + gRPC server. |
| `generate_stubs.sh`     | Generates `tokenizer_pb2*.py` from the proto. |
| `Dockerfile`            | Builds an image with libmecab + mecab-ko-dic + the server. |

## Run

```bash
# Docker (bundles mecab-ko-dic):
docker build -t milvus-mecab-tokenizer .
docker run -p 50051:50051 milvus-mecab-tokenizer

# or locally (needs libmecab + a Korean dic installed):
pip install -r requirements.txt
./generate_stubs.sh
python server.py --port 50051 --mecab-args "-d /usr/local/lib/mecab/dic/mecab-ko-dic"
```

Then point a Milvus analyzer at it (see `../02_grpc_mecab.py`):

```json
{"tokenizer": {"type": "grpc", "endpoint": "http://mecab-tokenizer:50051"}}
```

> The `endpoint` must be resolvable **from the Milvus process** (querynode /
> datanode), not just from your client.

## The offset contract (the part that's easy to get wrong)

`offset_from` / `offset_to` are **byte** offsets into the UTF-8 encoding of the
original text, `offset_to` exclusive. MeCab returns surface forms without byte
spans, so `mecab_analyze.tokenize()` recovers them by walking a cursor and locating
each surface in the source (which also skips the whitespace MeCab drops). Each Hangul
syllable is 3 UTF-8 bytes, so a char-index shortcut would corrupt highlighting and
phrase-match slop — hence the dedicated, tested function.

## POS filtering

By default the server drops particles (`J*`), endings (`E*`), and symbols (`S*`),
keeping content morphemes — the same idea as the `textsearch_ko` PostgreSQL
extension. Override per request through the analyzer `parameters`:

- `keep_pos` → whitelist of POS tags to keep (everything else dropped)
- `stop_pos` → blacklist of POS tags to drop (replaces the default set)
- `lowercase` → `["true"]` / `["false"]`

## Troubleshooting

- **`Failed initializing MeCab ... no such file or directory: /usr/local/etc/mecabrc`**
  — the `mecab-python3` wheel bundles its own libmecab and looks for a `mecabrc`
  even when you pass `-d`. Create one (the Docker image's dict path shown here):
  ```bash
  mkdir -p /usr/local/etc
  echo "dicdir = /usr/lib/x86_64-linux-gnu/mecab/dic/mecab-ko-dic" > /usr/local/etc/mecabrc
  ```
  or set `MECABRC=/etc/mecabrc`. (The Debian mecab-ko-dic build installs the dict
  under `/usr/lib/x86_64-linux-gnu/mecab/dic/mecab-ko-dic`, not `/usr/local/...`.)

## Production notes

Tokenization happens on **every** document at index time and **every** query, so
this service is on the hot path:

- Run it co-located (sidecar / same node) with the querynode to keep RPC latency low.
- Scale horizontally behind the endpoint; `MeCab.Tagger` is not thread-safe, so
  either use a tagger-per-thread pool or run multiple single-worker processes.
- Consider caching by text hash for repeated queries.
- Keep the dictionary version pinned and identical across replicas, or scores drift.
