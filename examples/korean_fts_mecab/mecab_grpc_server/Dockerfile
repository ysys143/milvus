# Reference image for the MeCab gRPC tokenizer (Korean / mecab-ko-dic).
#
# Build:  docker build -t milvus-mecab-tokenizer .
# Run:    docker run -p 50051:50051 milvus-mecab-tokenizer
#
# Then point a Milvus analyzer at it:
#   {"tokenizer": {"type": "grpc", "endpoint": "http://<host>:50051"}}
FROM python:3.11-slim

# System libmecab + Korean dictionary. On Debian/Ubuntu the Korean dic is not in
# the default repos, so we build mecab-ko-dic from source against libmecab.
RUN apt-get update && apt-get install -y --no-install-recommends \
        mecab libmecab-dev mecab-utils \
        build-essential automake curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# mecab-ko-dic (same dictionary family Milvus' lindera "ko-dic" uses). The Debian
# libmecab-dev dicdir is /usr/lib/x86_64-linux-gnu/mecab/dic, so `make install`
# lands the dict there (NOT /usr/local/...).
RUN cd /tmp \
    && curl -L -o ko-dic.tar.gz \
        https://bitbucket.org/eunjeon/mecab-ko-dic/downloads/mecab-ko-dic-2.1.1-20180720.tar.gz \
    && tar xzf ko-dic.tar.gz \
    && cd mecab-ko-dic-2.1.1-20180720 \
    && ./autogen.sh \
    && ./configure \
    && make \
    && make install \
    && ldconfig \
    && rm -rf /tmp/*

# The mecab-python3 wheel bundles its own libmecab and needs a mecabrc to exist.
RUN mkdir -p /usr/local/etc \
    && echo "dicdir = /usr/lib/x86_64-linux-gnu/mecab/dic/mecab-ko-dic" > /usr/local/etc/mecabrc

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tokenizer.proto mecab_analyze.py server.py generate_stubs.sh ./
RUN chmod +x generate_stubs.sh && ./generate_stubs.sh

EXPOSE 50051
CMD ["python", "server.py", "--port", "50051", \
     "--mecab-args", "-d /usr/lib/x86_64-linux-gnu/mecab/dic/mecab-ko-dic"]
