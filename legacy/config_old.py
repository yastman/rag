#!/usr/bin/env python3
"""
Configuration for Contextual RAG Pipeline
"""

import os

from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# =============================================================================
# API CONFIGURATION
# =============================================================================

# Z.AI API (Primary)
ZAI_API_KEY = os.getenv("ZAI_API_KEY")
ZAI_MODEL = "glm-4.6"
ZAI_MAX_TOKENS = 2048
ZAI_TEMPERATURE = 0.0
ZAI_RATE_LIMIT_DELAY = 1.2  # seconds between API calls

# Anthropic Claude API (Backup)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-3-haiku-20240307"
CLAUDE_MAX_TOKENS = 2048
CLAUDE_TEMPERATURE = 0.0
CLAUDE_RATE_LIMIT_DELAY = 1.2  # seconds between API calls

# Docling API
DOCLING_URL = os.getenv("DOCLING_URL", "http://localhost:5001")
DOCLING_TIMEOUT = 600  # 10 minutes for large PDFs

# BGE-M3 API
BGE_M3_URL = os.getenv("BGE_M3_URL", "http://localhost:8001")
BGE_M3_TIMEOUT = 60

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv(
    "QDRANT_API_KEY", "3e7321df905ee908fd95a959a0301b5a2d5eb2b5e6f709a7e31251a7386e8395"
)

# =============================================================================
# COLLECTION CONFIGURATION
# =============================================================================

# Single unified collection for all legal documents (2025-10-23)
# All documents (Criminal Code, Civil Code, Constitution, etc.) will be stored here
DEFAULT_COLLECTION = "legal_documents"

# Legacy collection names (deprecated - for reference only)
COLLECTION_BASELINE = "uk_civil_code_v2"
COLLECTION_CONTEXTUAL_KG = "uk_civil_code_contextual_kg"

# Vector dimensions (BGE-M3)
DENSE_VECTOR_SIZE = 1024
COLBERT_VECTOR_SIZE = 1024

# =============================================================================
# DOCUMENT CONFIGURATION
# =============================================================================

DOCUMENT_NAME = "Кримінальний кодекс України"
PDF_PATH = "/home/admin/contextual_rag/docs/documents/Кримінальний кодекс України - Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx"

# =============================================================================
# PROCESSING CONFIGURATION
# =============================================================================

# Testing limits
TEST_MAX_CHUNKS = 5  # For quick testing
FULL_PROCESSING = None  # None = process all chunks

# Rate limiting
CHUNK_PROCESSING_DELAY = 0.1  # seconds between chunks

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2

# =============================================================================
# SEARCH ENGINE CONFIGURATION
# =============================================================================

# Default search engine (2025-10-23: Switched to DBSF+ColBERT based on A/B test results)
# Options: "baseline", "hybrid", "dbsf_colbert"
# Performance: DBSF+ColBERT shows +2.9% Recall@1 vs Baseline (94.0% vs 91.3%)
DEFAULT_SEARCH_ENGINE = "dbsf_colbert"

# =============================================================================
# SEARCH OPTIMIZATION CONFIGURATION (Qdrant 2025 Best Practices)
# =============================================================================

# Score thresholds (filter out low-relevance results)
SCORE_THRESHOLD_DENSE = 0.5  # For dense-only search
SCORE_THRESHOLD_HYBRID = 0.3  # For DBSF fusion (more lenient, fusion normalizes)
SCORE_THRESHOLD_COLBERT = 0.4  # For ColBERT reranking

# HNSW search parameters (runtime precision tuning)
HNSW_EF_DEFAULT = 128  # Default HNSW ef parameter
HNSW_EF_HIGH_PRECISION = 256  # For higher precision at cost of latency
HNSW_EF_LOW_LATENCY = 64  # For faster search with lower precision

# Batch processing
BATCH_SIZE_QUERIES = 10  # Number of queries to batch in query_batch_points()
BATCH_SIZE_EMBEDDINGS = 32  # Number of texts to embed at once

# Retrieval stages
RETRIEVAL_LIMIT_STAGE1 = 100  # Dense+Sparse fusion candidates
RETRIEVAL_LIMIT_STAGE2 = 10  # Final results after ColBERT rerank

# Payload optimization (only fetch needed fields)
PAYLOAD_FIELDS_MINIMAL = ["article_number", "text"]
PAYLOAD_FIELDS_FULL = ["article_number", "text", "chapter_number", "section_number", "book_number"]

# MMR diversity parameters
MMR_LAMBDA = 0.5  # Balance between relevance (1.0) and diversity (0.0)

# =============================================================================
# EVALUATION CONFIGURATION
# =============================================================================

# Metrics
RECALL_K_VALUES = [1, 3, 5, 10]
NDCG_K_VALUES = [1, 3, 5, 10]
FAILURE_RATE_K_VALUES = [1, 3, 5, 10]

# Evaluation queries file
EVALUATION_QUERIES_FILE = "/home/admin/evaluation_queries.json"

# =============================================================================
# OUTPUT CONFIGURATION
# =============================================================================

# Log files
LOG_DIR = "/tmp"
TEST_LOG_PREFIX = "contextual_kg_test"

# Reports
REPORT_DIR = "/home/admin"
EVALUATION_RESULTS_FILE = f"{REPORT_DIR}/evaluation_results.json"
FINAL_REPORT_FILE = f"{REPORT_DIR}/NEXT_GEN_RAG_REPORT.md"

# =============================================================================
# VALIDATION
# =============================================================================


def validate_config():
    """Validate configuration before starting."""
    errors = []

    # Check required API keys (Z.AI primary, will use fallback if not available)
    if not ZAI_API_KEY:
        print("⚠️  WARNING: ZAI_API_KEY not set - will use fallback regex parser")

    # Check file existence
    import os.path

    if not os.path.exists(PDF_PATH):
        errors.append(f"PDF file not found: {PDF_PATH}")

    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        return False

    print("✅ Configuration validated successfully")
    return True


if __name__ == "__main__":
    print("=" * 80)
    print("CONTEXTUAL RAG - CONFIGURATION")
    print("=" * 80)
    print()
    print("API Configuration:")
    print(f"  Anthropic API Key: {'✓ Set' if ANTHROPIC_API_KEY else '✗ Not set'}")
    print(f"  Claude Model: {CLAUDE_MODEL}")
    print(f"  Docling URL: {DOCLING_URL}")
    print(f"  BGE-M3 URL: {BGE_M3_URL}")
    print(f"  Qdrant URL: {QDRANT_URL}")
    print()
    print("Collections:")
    print(f"  Baseline: {COLLECTION_BASELINE}")
    print(f"  Contextual+KG: {COLLECTION_CONTEXTUAL_KG}")
    print()
    print("Document:")
    print(f"  Name: {DOCUMENT_NAME}")
    print(f"  Path: {PDF_PATH}")
    print()
    print("=" * 80)
    print()

    validate_config()
