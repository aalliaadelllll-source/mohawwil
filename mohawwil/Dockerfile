FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng \
    libreoffice-writer fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# تشغيل بمستخدم عادي بدل root (أمان أفضل)
RUN useradd -m bot && mkdir -p data tmp && chown -R bot:bot /app
USER bot
VOLUME ["/app/data"]

CMD ["python", "main.py"]
