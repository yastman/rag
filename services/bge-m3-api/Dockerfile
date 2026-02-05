FROM python:3.12-slim
WORKDIR /app

***REMOVED*** Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

***REMOVED*** Install CPU-only torch first (separate index)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

***REMOVED*** Copy and install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

***REMOVED*** Copy application code
COPY config.py .
COPY app.py .

***REMOVED*** Environment for HF cache (will be mounted as volume)
ENV HF_HOME=/models/hf
ENV TRANSFORMERS_CACHE=/models/hf
ENV SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers

***REMOVED*** Concurrency settings
ENV OMP_NUM_THREADS=2
ENV MKL_NUM_THREADS=2

EXPOSE 8000

***REMOVED*** Run with limited concurrency for VPS
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "4"]
