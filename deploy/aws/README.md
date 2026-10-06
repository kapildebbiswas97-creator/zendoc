# AWS EC2 + Vercel deployment

Use the runbook at [docs/AWS_EC2_VERCEL_LAUNCH.md](../../docs/AWS_EC2_VERCEL_LAUNCH.md).

Architecture: Browser → existing Vercel public project → HTTPS AWS EC2 origin → Caddy → Flask + operations worker → **PostgreSQL 16 on a private Docker network**.

Files here are an AWS adaptation of the already reviewed Docker deployment. `ZENDOC_DEPLOYMENT_PLATFORM` reports `aws_ec2`. The optional TURN server and guarded PostgreSQL backup/restore scripts are preserved.

This is **not** proof that AWS infrastructure is live, nor that migration, data persistence, backups, email, durable media storage or public clinical release are verified. No third Vercel project is required.

Keep `deploy/aws/.env` private and out of Git. Do not delete or replace old Render/OCI data or backups until recovery and record parity are proven.
