FROM python:3.12-slim

# Tesseract OCR + орыс тілі пакеті, EasyOCR/Pillow үшін қажет либралар
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs images

# credentials.json және .env контейнерге volume/COPY арқылы қосылуы керек
CMD ["python", "main.py"]
