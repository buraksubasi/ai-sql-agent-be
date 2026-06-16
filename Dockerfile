FROM python:3.12-slim

# Sistem bağımlılıkları (psycopg2-binary için libpq gerekebilir)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Önce sadece requirements'ı kopyala → Docker layer cache'den faydalanır
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Kaynak kodunu kopyala (.dockerignore ile gereksizler zaten dışarıda)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
