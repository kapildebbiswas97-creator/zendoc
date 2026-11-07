# =============================================================================
# ZENDOC 2.0 Python Worker — Production Multi-Stage Containerfile
# =============================================================================

# --- Stage 1: Build Dependencies ---
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY worker/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Minimal Runtime Image ---
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -r zendoc && useradd -r -g zendoc -d /app -s /sbin/nologin zendoc

# Copy installed python wheels from builder stage
COPY --from=builder /root/.local /home/zendoc/.local
ENV PATH=/home/zendoc/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Copy worker application source
COPY --chown=zendoc:zendoc worker /app/worker

USER zendoc

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["python", "-m", "worker.app"]
