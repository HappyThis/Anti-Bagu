#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-anti-bagu}"
REMOTE_CURRENT=/opt/anti-bagu
REMOTE_STAGE=/opt/anti-bagu.next

npm --prefix apps/web run build
make package-agent

ssh "$TARGET" "
  set -euo pipefail
  install -d -o antibagu -g antibagu -m 0755 ${REMOTE_STAGE}
"

rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env.local' \
  --exclude '.runtime/' \
  --exclude 'apps/web/node_modules/' \
  --exclude 'apps/capture-macos/.build/' \
  ./ "${TARGET}:${REMOTE_STAGE}/"

ssh "$TARGET" "
  set -euo pipefail
  CURRENT=${REMOTE_CURRENT}
  STAGE=${REMOTE_STAGE}
  PREVIOUS=/opt/anti-bagu.previous
  FAILED=/opt/anti-bagu.failed

  chown -R antibagu:antibagu \"\${STAGE}\"
  sudo -u antibagu python3 -m venv --clear \"\${STAGE}/.venv\"
  sudo -u antibagu \"\${STAGE}/.venv/bin/pip\" install \
    -i https://mirrors.aliyun.com/pypi/simple/ -e \"\${STAGE}/backend\"
  cd \"\${STAGE}\"
  sudo -u antibagu bash -lc \
    'set -a; source /etc/anti-bagu/anti-bagu.env; set +a; .venv/bin/alembic -c backend/alembic.ini upgrade head'

  install -m 0644 \"\${STAGE}/deploy/systemd/anti-bagu.service\" \
    /etc/systemd/system/anti-bagu.service
  install -m 0644 \"\${STAGE}/deploy/nginx/anti-bagu.conf\" \
    /etc/nginx/sites-available/anti-bagu
  ln -sfn /etc/nginx/sites-available/anti-bagu /etc/nginx/sites-enabled/anti-bagu
  nginx -t
  systemctl daemon-reload

  rm -rf -- \"\${PREVIOUS}\" \"\${FAILED}\"
  if [[ -e \"\${CURRENT}\" ]]; then
    mv \"\${CURRENT}\" \"\${PREVIOUS}\"
  fi
  mv \"\${STAGE}\" \"\${CURRENT}\"

  rollback() {
    systemctl stop anti-bagu || true
    if [[ -e \"\${CURRENT}\" ]]; then
      mv \"\${CURRENT}\" \"\${FAILED}\"
    fi
    if [[ -e \"\${PREVIOUS}\" ]]; then
      mv \"\${PREVIOUS}\" \"\${CURRENT}\"
      systemctl restart anti-bagu
    fi
  }

  if ! systemctl restart anti-bagu; then
    rollback
    exit 1
  fi

  healthy=false
  for _ in {1..15}; do
    if curl -fsS http://127.0.0.1:8765/health >/dev/null; then
      healthy=true
      break
    fi
    sleep 1
  done
  if [[ \"\${healthy}\" != true ]]; then
    rollback
    exit 1
  fi

  systemctl reload nginx
"
