"""Approach 1 -- Korean full-text search with Milvus' built-in `lindera` tokenizer.

`lindera` + `dict_kind: "ko-dic"` runs morphological analysis in-process using the
*same* `mecab-ko-dic-2.1.1` dictionary that mecab-ko uses (see
internal/core/thirdparty/tantivy/tantivy-binding/src/analyzer/dict/lindera/ko_dic.rs).
The engine is a pure-Rust reimplementation, so there is no libmecab to install and
no Milvus rebuild -- the analyzer is configured entirely through schema params.

The `korean_stop_tags` filter drops particles / endings by POS tag, reproducing the
content-word filtering the textsearch_ko PostgreSQL extension performs
(무궁화꽃이 피었습니다 -> 무궁화 / 꽃 / 피).

Prereqs:
    pip install "pymilvus>=2.5"
    a running Milvus (e.g. scripts/standalone_embed.sh, or Milvus 3.x)
On first use Milvus downloads + builds ko-dic into its dict cache
(default /var/lib/milvus/dict/lindera), which can take a moment.
"""

from pymilvus import DataType, Function, FunctionType, MilvusClient

COLLECTION = "kfts_lindera_kodic"

# Keep only content POS (mecab-ko-dic tagset): nouns, verbs, adjectives, adverbs,
# determiners, foreign words, numbers, roots. Everything else -- particles (조사),
# endings (어미), whitespace, symbols -- is dropped. This yields the same
# content-word reduction the textsearch_ko PostgreSQL extension performs
# (무궁화꽃이 피었습니다 -> 무궁화 / 꽃 / 피).
#
# NOTE: a keep-list (korean_keep_tags) is used rather than a stop-list. Empirically,
# against this lindera ko-dic build, korean_stop_tags matched content tags (e.g.
# "NNG") but NOT the particle/ending codes one would guess from the raw
# mecab-ko-dic tagset (e.g. "JKS"/"EP"), so a blacklist silently let particles
# through. Whitelisting content POS is both robust and the usual choice for BM25.
# (There is also a `korean_stop_tags` filter for the inverse policy.)
KOREAN_KEEP_TAGS = [
    "NNG", "NNP", "NNB", "NR", "NP",   # nouns / numerals / pronouns
    "VV", "VA", "VX",                    # verbs / adjectives / auxiliary predicates
    "MAG", "MAJ", "MM",                  # adverbs / determiners
    "SL", "SH", "SN",                    # foreign words / Hanja / numbers
    "XR",                                # roots
]

analyzer_params = {
    "tokenizer": {
        "type": "lindera",
        "dict_kind": "ko-dic",
        "mode": "normal",  # "decompose" splits compounds more aggressively
        # POS filter runs *inside* the lindera tokenizer (not the top-level filter)
        "filter": [
            {"kind": "korean_keep_tags", "tags": KOREAN_KEEP_TAGS},
        ],
    },
    # top-level analyzer filters (system filters): lowercase Latin tokens
    "filter": ["lowercase"],
}

DOCS = [
    "무궁화꽃이 피었습니다",
    "벡터 데이터베이스 Milvus는 전문 검색을 지원합니다",
    "한국어 형태소 분석기를 붙여서 BM25 검색 품질을 높인다",
    "엘라스틱서치 없이 밀버스만으로 하이브리드 검색을 구현했다",
]


def main():
    client = MilvusClient(uri="http://localhost:19530")

    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)

    schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field(
        "text",
        DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
        analyzer_params=analyzer_params,
    )
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)

    # BM25 turns the analyzed `text` into the `sparse` vector automatically.
    schema.add_function(
        Function(
            name="text_bm25",
            input_field_names=["text"],
            output_field_names=["sparse"],
            function_type=FunctionType.BM25,
        )
    )

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="sparse",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
    )

    client.create_collection(COLLECTION, schema=schema, index_params=index_params)
    client.insert(COLLECTION, [{"text": d} for d in DOCS])
    client.flush(COLLECTION)

    # Inspect tokenization directly (great for debugging analyzer config).
    run = client.run_analyzer("무궁화꽃이 피었습니다", analyzer_params=analyzer_params)
    print("tokens for '무궁화꽃이 피었습니다':", run)

    res = client.search(
        COLLECTION,
        data=["무궁화 검색"],
        anns_field="sparse",
        limit=3,
        output_fields=["text"],
    )
    print("\nBM25 results for '무궁화 검색':")
    for hit in res[0]:
        print(f"  score={hit['distance']:.4f}  {hit['entity']['text']}")


if __name__ == "__main__":
    main()
