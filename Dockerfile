FROM python:3.12-slim

# Tesseract OCR + орыс тілі пакеті, Pillow үшін қажет либралар
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-easyocr.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# EasyOCR/torch (~2GB) әдепкі бойынша орнатылмайды, себебі әдепкі
# OCR_ENGINE=tesseract (жеңіл әрі жылдам іске қосылады). Егер .env
# файлында OCR_ENGINE=easyocr қойғыңыз келсе, келесі жолдың
# комментарийін алып тастаңыз:
# RUN pip install --no-cache-dir -r requirements-easyocr.txt

COPY . .

RUN mkdir -p logs

# credentials.json және .env контейнерге volume/COPY арқылы қосылуы керек
CMD ["python", "main.py"]
