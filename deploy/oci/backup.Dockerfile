FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/zendoc
COPY scripts/postgres_backup.py /opt/zendoc/scripts/postgres_backup.py
COPY scripts/verify_postgres_backup.py /opt/zendoc/scripts/verify_postgres_backup.py

ENTRYPOINT ["python", "/opt/zendoc/scripts/postgres_backup.py"]
