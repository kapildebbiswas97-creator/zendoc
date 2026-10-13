#!/bin/sh
set -eu

: "${ZENDOC_TURN_SHARED_SECRET:?set ZENDOC_TURN_SHARED_SECRET in deploy/aws/.env}"
: "${ZENDOC_TURN_EXTERNAL_IP:?set ZENDOC_TURN_EXTERNAL_IP to the AWS EC2 public IP}"
: "${ZENDOC_TURN_REALM:?set ZENDOC_TURN_REALM}"

case "${ZENDOC_TURN_EXTERNAL_IP}" in
  *[!0-9a-fA-F:.]*) echo "Invalid ZENDOC_TURN_EXTERNAL_IP" >&2; exit 2 ;;
esac

LISTEN_PORT="${ZENDOC_TURN_PORT:-3478}"
MIN_PORT="${ZENDOC_TURN_MIN_RELAY_PORT:-49160}"
MAX_PORT="${ZENDOC_TURN_MAX_RELAY_PORT:-49200}"

umask 077
cat > /tmp/zendoc-turnserver.conf <<EOF
listening-port=${LISTEN_PORT}
fingerprint
use-auth-secret
static-auth-secret=${ZENDOC_TURN_SHARED_SECRET}
realm=${ZENDOC_TURN_REALM}
external-ip=${ZENDOC_TURN_EXTERNAL_IP}
min-port=${MIN_PORT}
max-port=${MAX_PORT}
stale-nonce=600
user-quota=12
total-quota=240
no-loopback-peers
no-multicast-peers
no-tcp-relay
simple-log
log-file=stdout
EOF

exec turnserver -c /tmp/zendoc-turnserver.conf
