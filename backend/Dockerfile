FROM python:3.12-slim

WORKDIR /app

# Deps del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      fastapi 'uvicorn[standard]' 'pydantic[email]' pydantic-settings \
      'sqlalchemy[asyncio]' asyncpg alembic httpx structlog openai \
      python-json-logger tenacity argon2-cffi authlib itsdangerous \
      pdfplumber python-docx openpyxl python-multipart pgvector \
      pytrends

# Código
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# Aplica migraciones y arranca Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]