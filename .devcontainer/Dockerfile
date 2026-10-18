FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 postgresql-client openssl ca-certificates nginx \
    && rm -rf /var/lib/apt/lists/*
