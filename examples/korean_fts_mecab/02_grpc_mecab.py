"""Approach 2 -- Korean full-text search with a real MeCab via Milvus' `grpc` tokenizer.

Milvus delegates tokenization to an external gRPC service (see mecab_grpc_server/),
so you can run the actual libmecab (mecab-ko) with your own dictionary / user
dictionary / tuning -- no Milvus rebuild. This is the closest analogue to linking
libmecab into a PostgreSQL C extension, but the language boundary is crossed by RPC.

Prereqs:
    pip install "pymilvus>=2.5"
    a running Milvus
    the MeCab tokenizer server running and reachable from Milvus:
        cd mecab_grpc_server && docker build -t milvus-mecab-tokenizer . \
            && docker run -p 50051:50051 milvus-mecab-tokenizer
    # endpoint below must be resolvable FROM the Milvus process, not just this client
"""

from pymilvus import DataType, Function, FunctionType, MilvusClient

COLLECTION = "kfts_grpc_mecab"
MECAB_ENDPOINT = "http://localhost:50051"  # as seen by the Milvus server

analyzer_params = {
    "tokenizer": {
        "type": "grpc",
        "endpoint": MECAB_ENDPOINT,
        # forwarded to the server as TokenizationRequest.parameters; optional.
        # here we let the server keep only these POS tags (content words):
        "parameters": [
            {
                "key": "keep_pos",
                "values": ["NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "VX",
                           "MAG", "MAJ", "MM", "SL", "SH", "SN"],
            },
        ],
        # if the server is briefly unreachable, index/query with these instead of
        # failing the whole request (optional safety net):
        "default_tokens": [],
    },
    "filter": ["lowercase"],
}

DOCS = [
    "무궁화꽃이 피었습니다",
    "벡터 데이터베이스 Milvus는 전문 검색을 지원합니다",
    "사용자 사전에 등록한 신조어도 MeCab이 한 토큰으로 잡는다",
]


def main():
    client = MilvusClient(uri="http://localhost:19530")

    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)

    schema = client.create_schema(auto_id=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field(
        "text",
        DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
        analyzer_params=analyzer_params,
    )
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
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
        field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25"
    )

    client.create_collection(COLLECTION, schema=schema, index_params=index_params)
    client.insert(COLLECTION, [{"text": d} for d in DOCS])
    client.flush(COLLECTION)

    res = client.search(
        COLLECTION,
        data=["전문 검색"],
        anns_field="sparse",
        limit=3,
        output_fields=["text"],
    )
    print("BM25 results for '전문 검색':")
    for hit in res[0]:
        print(f"  score={hit['distance']:.4f}  {hit['entity']['text']}")


if __name__ == "__main__":
    main()
