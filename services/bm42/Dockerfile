FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.32.0 \
    fastembed>=0.7.0 \
    pydantic>=2.0.0

# Copy service code
COPY main.py .

# Pre-download model during build (cached in image)
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm42-all-minilm-l6-v2-attentions')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
