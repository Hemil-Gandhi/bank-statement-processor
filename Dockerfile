FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract (OCR), Poppler (PDF helpers) and OpenCV runtime libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-hin \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend
COPY scripts /app/scripts
COPY docs /app/docs
COPY samples /app/samples
COPY README.md /app/README.md
COPY ACCEPTANCE_CHECKLIST.md /app/ACCEPTANCE_CHECKLIST.md

# Keep the trained model and training set outside the writable data volume so a
# fresh Docker volume still starts with a working classifier.
RUN mkdir -p /app/model /app/training /app/data \
    && cp /app/backend/data/models/classifier.joblib /app/model/classifier.joblib \
    && cp /app/backend/data/training/transactions_labeled.csv /app/training/transactions_labeled.csv

ENV PYTHONPATH=/app/backend \
    BSP_DATA_DIR=/app/data \
    BSP_MODEL_PATH=/app/model/classifier.joblib \
    BSP_TRAINING_CSV=/app/training/transactions_labeled.csv \
    BSP_FRONTEND_DIR=/app/frontend \
    BSP_DOCS_DIR=/app/docs \
    BSP_SAMPLES_DIR=/app/samples \
    BSP_LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=6s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
