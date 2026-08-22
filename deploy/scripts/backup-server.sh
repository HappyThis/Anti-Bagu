#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT=/var/lib/anti-bagu/backups
STAMP=$(date +%Y-%m-%d-%H%M%S)
TARGET="${BACKUP_ROOT}/${STAMP}"

install -d -o root -g antibagu -m 0750 "$TARGET"
runuser -u postgres -- pg_dump --format=custom anti_bagu > "${TARGET}/anti_bagu.pgdump"
BACKUP_ITEMS=(storage logs)
if [[ -f /var/lib/anti-bagu/credential-encryption.key ]]; then
  BACKUP_ITEMS+=(credential-encryption.key)
fi
tar -czf "${TARGET}/task-storage.tar.gz" -C /var/lib/anti-bagu "${BACKUP_ITEMS[@]}"
sha256sum "${TARGET}/anti_bagu.pgdump" "${TARGET}/task-storage.tar.gz" > "${TARGET}/SHA256SUMS"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf -- {} +
