# Domainless OCI staging

This mode serves ZENDOC directly at an OCI public IPv4 address with HTTPS. It needs no custom domain and no Vercel project. The app UI and API are served by the existing Flask container; PostgreSQL remains private inside Docker.

Use it for a synthetic-data feedback beta. Do not put real patient or health records on this free staging VM.

## Cost target and limits

OCI documents Always Free resources as free for the life of an account. The current allocation includes up to 2 OCPUs and 12 GB RAM on Ampere A1, 200 GB of combined boot/block storage in the home region, and 10 TB monthly outbound transfer. Public IPv4 addresses are also free according to Oracle's networking documentation. Stay within the Always Free limits and create only resources shown as Always Free eligible.

This targets a $0 twelve-month test period; it is not an uptime guarantee. OCI can reclaim an Always Free VM if CPU, network and (for A1) memory usage all stay below its thresholds for seven days. Keep a separate backup of any test data worth retaining. If capacity is unavailable in the account's home region, wait or choose another availability domain; do not switch to a paid shape.

## OCI instance setup

Create one Ubuntu 24.04 Always Free eligible VM in the tenancy's home region:

- Shape: \`VM.Standard.A1.Flex\`, 2 OCPUs and 12 GB memory.
- Boot volume: 50 GB.
- Assign the public IPv4 address.
- Ingress: TCP 80 and 443 from the internet; TCP 22 only from the operator's trusted IP. Never open TCP 5432.
- Do not add a paid load balancer, NAT gateway, storage, or other paid service.

The VM public IPv4 is the staging URL host. OCI keeps an ephemeral IP assigned for the life of the instance; reserve the IP only if you have a specific reason to reassign it.

## Deploy

Install Docker Engine and Compose on the VM, then check out the reviewed staging commit:

\`\`\`bash
git clone https://github.com/kapildebbiswas97-creator/zendoc.git
cd zendoc
git checkout staging/ip-origin-tls
git rev-parse HEAD
\`\`\`

The OCI IP mode is included in the open staging PR. Deploy only after its CI checks pass and the change is merged or explicitly reviewed for staging.

Create the private environment file:

\`\`\`bash
cp deploy/oci/.env.example deploy/oci/.env
chmod 600 deploy/oci/.env
\`\`\`

Set these values in \`deploy/oci/.env\`:

- \`ZENDOC_DOMAIN\`: the OCI VM public IPv4, without a scheme.
- \`ZENDOC_PUBLIC_BASE_URL\`: \`https://<OCI_PUBLIC_IPV4>\`.
- \`ZENDOC_TLS_EMAIL\`: an operator email for certificate notices.
- \`ZENDOC_GIT_COMMIT\`: the checked-out 40-character commit.
- Separate long random values for \`ZENDOC_GATEWAY_TOKEN\`, \`POSTGRES_PASSWORD\`, \`ZENDOC_SECRET_KEY\`, and \`ZENDOC_ADMIN_PASSWORD\`.
- A unique \`ZENDOC_ADMIN_EMAIL\`.

Keep \`ZENDOC_PERSISTENCE_VERIFIED\`, \`ZENDOC_BACKUP_VERIFIED\`, and \`ZENDOC_PUBLIC_RELEASE_REQUIRED\` false until their real checks pass. Keep the gateway token private even though this direct-IP Caddy mode does not use it.

From \`deploy/oci\`, validate and start the stack:

\`\`\`bash
docker compose --env-file .env -f compose.yaml -f compose.ip-origin.yaml config --quiet
docker compose --env-file .env -f compose.yaml -f compose.ip-origin.yaml up -d --build
docker compose --env-file .env -f compose.yaml -f compose.ip-origin.yaml ps
\`\`\`

Caddy obtains and renews a Let's Encrypt short-lived IP certificate automatically. These certificates expire after 160 hours, so leave Caddy running and keep its \`caddy_data\` volume. The hostname is the literal IP; the browser URL is:

\`\`\`text
https://<OCI_PUBLIC_IPV4>
\`\`\`

## Verify and share

Wait for the certificate and app health checks, then run:

\`\`\`bash
curl -fsS https://<OCI_PUBLIC_IPV4>/api/v1/health
curl -fsS https://<OCI_PUBLIC_IPV4>/api/v1/ready
python scripts/verify_deployment.py https://<OCI_PUBLIC_IPV4> --expected-commit <COMMIT_SHA> --require-platform oci --require-engine postgresql
\`\`\`

Confirm that readiness reports PostgreSQL and the expected commit. Test login, invitation-only access and logout with synthetic accounts. Do not claim backups or persistence are verified until the restart and restore checks in [the OCI zero-budget runbook](OCI_ZERO_BUDGET_LAUNCH.md) pass.

Share only the HTTPS IP URL with beta testers. The direct IP is an interim staging address; a paid domain can be added after the feedback period. If the instance is terminated and recreated, the IP and certificate identity can change.
