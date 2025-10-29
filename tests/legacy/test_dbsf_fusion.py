#!/usr/bin/env python3
"""
Test: Verify if Qdrant accepts "fusion": "dbsf" or only "fusion": "rrf"
"""

import sys
import requests
import json

sys.path.append("/srv/contextual_rag")
from config import QDRANT_URL, QDRANT_API_KEY
from FlagEmbedding import BGEM3FlagModel

# Load model
print("Loading BGE-M3...")
model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
print("✓ Model loaded\n")

# Test query
query = "какое наказание за кражу"
print(f"Query: {query}\n")

# Get embeddings
embeddings = model.encode(query, return_dense=True, return_sparse=True, return_colbert_vecs=True)
dense = embeddings["dense_vecs"].tolist()
sparse = embeddings["lexical_weights"]
sparse_indices = [int(k) for k in sparse.keys()]
sparse_values = [float(v) for v in sparse.values()]
colbert = embeddings["colbert_vecs"].tolist()

collection = "uk_civil_code_v2"
headers = {"api-key": QDRANT_API_KEY}

# Test 1: DBSF fusion (what we currently use)
print("=" * 80)
print("TEST 1: fusion='dbsf' (current implementation)")
print("=" * 80)

payload_dbsf = {
    "prefetch": [
        {
            "prefetch": [
                {"query": dense, "using": "dense", "limit": 10},
                {"query": {"values": sparse_values, "indices": sparse_indices}, "using": "sparse", "limit": 10},
            ],
            "query": {"fusion": "dbsf"},  # ← DBSF
        }
    ],
    "query": colbert,
    "using": "colbert",
    "limit": 3,
}

response = requests.post(
    f"{QDRANT_URL}/collections/{collection}/points/query",
    json=payload_dbsf,
    headers=headers,
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✓ Request successful")
    results = response.json()
    print(f"✓ Got {len(results.get('result', {}).get('points', []))} results")
else:
    print(f"✗ Request failed: {response.text}")

print()

# Test 2: RRF fusion (official Qdrant method)
print("=" * 80)
print("TEST 2: fusion='rrf' (official Qdrant method)")
print("=" * 80)

payload_rrf = {
    "prefetch": [
        {
            "prefetch": [
                {"query": dense, "using": "dense", "limit": 10},
                {"query": {"values": sparse_values, "indices": sparse_indices}, "using": "sparse", "limit": 10},
            ],
            "query": {"fusion": "rrf"},  # ← RRF
        }
    ],
    "query": colbert,
    "using": "colbert",
    "limit": 3,
}

response = requests.post(
    f"{QDRANT_URL}/collections/{collection}/points/query",
    json=payload_rrf,
    headers=headers,
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✓ Request successful")
    results = response.json()
    print(f"✓ Got {len(results.get('result', {}).get('points', []))} results")
else:
    print(f"✗ Request failed: {response.text}")

print()
print("=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("If both methods work, we need to A/B test them to see which is better.")
print("If only RRF works, we should update our code to use the official method.")
