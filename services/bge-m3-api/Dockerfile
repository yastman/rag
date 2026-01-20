FROM python:3.11-slim

***REMOVED*** Set working directory
WORKDIR /app

***REMOVED*** Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

***REMOVED*** Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

***REMOVED*** Copy application files
COPY app.py config.py ./

***REMOVED*** Create model cache directory
RUN mkdir -p /models

***REMOVED*** Set environment variables
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4

***REMOVED*** Expose port
EXPOSE 8000

***REMOVED*** Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

***REMOVED*** Run application
CMD ["python", "app.py"]
