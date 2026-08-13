#!/usr/bin/env bash
# Generate the Python gRPC stubs (tokenizer_pb2.py / tokenizer_pb2_grpc.py) from
# tokenizer.proto. Run once before starting the server, and again whenever the
# proto changes. Requires: pip install grpcio-tools
set -euo pipefail
cd "$(dirname "$0")"

python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  tokenizer.proto

echo "generated: tokenizer_pb2.py tokenizer_pb2_grpc.py"
