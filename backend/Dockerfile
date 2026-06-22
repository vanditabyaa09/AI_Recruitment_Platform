FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

# Shell form so ${PORT} expands. Platforms like Render/Railway inject $PORT;
# fall back to 8000 for local/compose. Single worker is intentional — the
# Chroma persistent client and in-process caches are not shared across workers.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
