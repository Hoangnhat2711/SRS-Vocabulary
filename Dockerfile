FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/vocab_sets

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn srs_fastapi:app --host 0.0.0.0 --port ${PORT:-8000}"]
