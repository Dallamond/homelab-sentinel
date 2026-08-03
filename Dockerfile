FROM python:3.12-slim

# journalctl (para el collector de journald) + certificados TLS
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY rules.example.yaml ./rules.example.yaml

RUN mkdir -p /app/data

EXPOSE 8088

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
