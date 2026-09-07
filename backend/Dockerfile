FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/hf_cache

WORKDIR /app

# System deps: libpq for psycopg, build tools for any C-extension wheels
# that don't ship prebuilt binaries for the target platform, curl for the
# HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh
RUN mkdir -p /app/data/uploads /app/data/hf_cache

# Note: intentionally still root. A non-root USER here would need the
# named volumes at /app/data/* (uploads, HF model cache) to already be
# writable by that UID, which Docker doesn't guarantee for a freshly
# created named volume on every host — getting that wrong silently breaks
# uploads/model downloads, which matters more for this project than the
# hardening does. Tracked as a real future improvement (see README), to be
# done properly (fix ownership at container start, then drop privileges)
# once it can be verified against real Docker rather than guessed at.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
