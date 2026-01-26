# Qdrant Connection Guide

## Overview

Qdrant is deployed on a remote server and is accessible both locally (on the server) and remotely (from your machine).

### Server Information

- **IP Address**: 95.111.252.29
- **SSH Port**: 1654
- **SSH User**: admin
- **SSH Key**: ~/.ssh/vps_access_key
- **Connection Alias**: `vps` (defined in ~/.zshrc)

### Qdrant Information

- **Version**: 1.15.4
- **Docker Container**: `ai-qdrant`
- **HTTP Port**: 6333
- **gRPC Port**: 6334
- **API Key**: 3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395

## Current State

### Collections

Currently there is **1 collection**:

**legal_documents**
- Points (vectors): 1,294
- Indexed vectors: 3,878
- Status: GREEN (healthy)
- Vector configuration:
  - **dense**: 1024-dimensional, Cosine similarity, HNSW index (M=16, ef_construct=200)
    - Quantization: int8 (scalar)
    - On-disk storage
  - **colbert**: 1024-dimensional, Cosine similarity, multi-vector (max_sim)
    - HNSW disabled (M=0)
  - **sparse**: IDF modifier for sparse vectors

## Connection Configuration

### 1. For Local Development (from your machine)

Use the main `.env` file:

```bash
# .env
QDRANT_URL=http://95.111.252.29:6333
QDRANT_API_KEY=3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395
```

### 2. For Working on the Server

Use `.env.server`:

```bash
# Copy server configuration
cp .env.server .env

# Or create a symbolic link
ln -sf .env.server .env
```

Contents of `.env.server`:
```bash
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395
```

## Connection Testing

### 1. Via curl (from local machine)

```bash
# Get list of collections
curl -s -H 'api-key: 3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395' \
  http://95.111.252.29:6333/collections

# Information about a specific collection
curl -s -H 'api-key: 3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395' \
  http://95.111.252.29:6333/collections/legal_documents
```

### 2. Via curl (on the server)

```bash
# Connect to the server
ssh -i ~/.ssh/vps_access_key -p 1654 admin@95.111.252.29

# Or using the alias from ~/.zshrc
zsh -c "$(grep 'alias vps=' ~/.zshrc | cut -d'=' -f2-)"

# Check collections
curl -s -H 'api-key: 3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395' \
  http://localhost:6333/collections
```

### 3. Via Python (test script)

A test script `test_qdrant_connection.py` has been created:

```bash
# On the server (with dependencies installed)
python3 test_qdrant_connection.py

# Or via poetry (if installed)
poetry run python test_qdrant_connection.py
```

### 4. Docker Container Check

```bash
# On the server
ssh -i ~/.ssh/vps_access_key -p 1654 admin@95.111.252.29 \
  "docker ps | grep qdrant"

# Output:
# 218ec1ea2aa1   qdrant/qdrant:v1.15.4   Up 2 hours (healthy)
```

## Usage in Code

### Python (qdrant-client)

```python
from qdrant_client import QdrantClient
from src.config.settings import Settings

# Load settings from .env
settings = Settings()

# Create client
client = QdrantClient(
    url=settings.qdrant_url,  # Automatically loaded from .env
    api_key=settings.qdrant_api_key
)

# Get collections
collections = client.get_collections()
print(f"Collections: {len(collections.collections)}")

# Get collection information
info = client.get_collection("legal_documents")
print(f"Points: {info.points_count}")
```

## Important Notes

1. **API key is required**: Qdrant is configured with mandatory authentication
2. **Ports are open**: Ports 6333 and 6334 are accessible from outside (0.0.0.0)
3. **Two configuration options**:
   - `.env` - for local development (remote connection)
   - `.env.server` - for running on the server (localhost)
4. **Security**: API key is stored in .env (added to .gitignore)

## Troubleshooting

### Error: "Must provide an API key"

Make sure you are passing the API key:
- In curl: `-H 'api-key: YOUR_KEY'`
- In Python: `api_key=settings.qdrant_api_key`

### Error: "Connection refused"

1. Check that Qdrant is running: `docker ps | grep qdrant`
2. Check that the URL in .env is correct
3. Check that port 6333 is accessible

### Error: "ModuleNotFoundError: qdrant_client"

Install dependencies:
```bash
# Via poetry
poetry install

# Via pip (in a virtual environment)
python3 -m venv .venv
source .venv/bin/activate
pip install qdrant-client python-dotenv sentence-transformers
```

## Useful Commands

```bash
# Connect to the server via SSH
ssh -i ~/.ssh/vps_access_key -p 1654 admin@95.111.252.29

# Check container status
docker ps -a | grep qdrant

# Qdrant logs
docker logs ai-qdrant --tail 100

# Restart Qdrant
docker restart ai-qdrant

# Check resource usage
docker stats ai-qdrant --no-stream
```

## Additional Information

- **Qdrant Documentation**: https://qdrant.tech/documentation/
- **API Reference**: https://qdrant.tech/documentation/api-reference/
- **Python Client**: https://github.com/qdrant/qdrant-client

---

**Last Updated**: 2025-10-29
**Status**: ✅ Connection configured and tested
