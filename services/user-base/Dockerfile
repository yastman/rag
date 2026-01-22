FROM python:3.12-slim

WORKDIR /app

# Install PyTorch CPU-only first (saves ~2GB vs CUDA)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.32.0 \
    sentence-transformers>=2.2.0 \
    pydantic>=2.0.0

# Copy service code
COPY main.py .

# Pre-download model during build (cached in image)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-base')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
