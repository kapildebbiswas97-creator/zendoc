FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "psycopg[binary]>=3.3.5,<4.0" \
    && groupadd --system --gid 10001 zendocbackup \
    && useradd --system --uid 10001 --gid zendocbackup \
       --home-dir /nonexistent --shell /usr/sbin/nologin zendocbackup

WORKDIR /opt/zendoc
COPY --chown=zendocbackup:zendocbackup scripts/postgres_backup.py /opt/zendoc/scripts/postgres_backup.py
COPY --chown=zendocbackup:zendocbackup scripts/verify_postgres_backup.py /opt/zendoc/scripts/verify_postgres_backup.py
COPY --chown=zendocbackup:zendocbackup scripts/postgres_restore.py /opt/zendoc/scripts/postgres_restore.py

# The host must explicitly grant UID 10001 write access to /var/backups/zendoc.
# Never silently chmod the host directory or run backup as root.
RUN mkdir -p /backups && chown zendocbackup:zendocbackup /backups
USER zendocbackup:zendocbackup
ENTRYPOINT ["python", "/opt/zendoc/scripts/postgres_backup.py"]
