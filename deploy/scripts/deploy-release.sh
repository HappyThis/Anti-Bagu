#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-anti-bagu}"
REMOTE_RELEASE=/opt/anti-bagu

npm --prefix apps/web run build
make package-agent

rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env.local' \
  --exclude '.runtime/' \
  --exclude 'apps/web/node_modules/' \
  --exclude 'apps/capture-macos/.build/' \
  ./ "${TARGET}:${REMOTE_RELEASE}/"

ssh "$TARGET" "
  set -euo pipefail
  chown -R antibagu:antibagu ${REMOTE_RELEASE}
  sudo -u antibagu python3 -m venv ${REMOTE_RELEASE}/.venv
  sudo -u antibagu ${REMOTE_RELEASE}/.venv/bin/pip install -i https://mirrors.aliyun.com/pypi/simple/ -e ${REMOTE_RELEASE}/backend
  cd ${REMOTE_RELEASE}
  sudo -u antibagu bash -lc 'set -a; source /etc/anti-bagu/anti-bagu.env; set +a; .venv/bin/alembic -c backend/alembic.ini upgrade head'
  install -m 0644 ${REMOTE_RELEASE}/deploy/systemd/anti-bagu.service /etc/systemd/system/anti-bagu.service
  systemctl daemon-reload
  systemctl restart anti-bagu
  nginx -t
  systemctl reload nginx
"
