FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Install dependencies at build time as root; runtime never needs root.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fixed UID/GID allows explicit ownership of upload/instance directories.
# Docker named volumes inherit these permissions on first creation.
RUN groupadd --system --gid 10001 zendoc \
    && useradd --system --uid 10001 --gid zendoc \
      --home-dir /nonexistent --shell /usr/sbin/nologin zendoc
COPY --chown=zendoc:zendoc . .
RUN mkdir -p /app/uploads /app/instance \
    && chown -R zendoc:zendoc /app/uploads /app/instance

USER zendoc:zendoc
EXPOSE 5000
CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:5000"]
