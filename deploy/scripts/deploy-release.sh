#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-anti-bagu}"
STAMP="$(date +%Y%m%d%H%M%S)"
REMOTE_CURRENT=/opt/anti-bagu
REMOTE_RELEASE_ROOT=/opt/anti-bagu.releases
REMOTE_RELEASE="${REMOTE_RELEASE_ROOT}/${STAMP}"

npm --prefix apps/web run build
make package-agent

ssh "$TARGET" "
  set -euo pipefail
  install -d -o antibagu -g antibagu -m 0755 ${REMOTE_RELEASE_ROOT}
  install -d -o antibagu -g antibagu -m 0755 ${REMOTE_RELEASE}
"

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
  CURRENT=${REMOTE_CURRENT}
  RELEASE_ROOT=${REMOTE_RELEASE_ROOT}
  RELEASE=${REMOTE_RELEASE}
  PREVIOUS_TARGET=''

  chown -R antibagu:antibagu \"\${RELEASE}\"
  sudo -u antibagu python3 -m venv \"\${RELEASE}/.venv\"
  sudo -u antibagu \"\${RELEASE}/.venv/bin/pip\" install \
    -i https://mirrors.aliyun.com/pypi/simple/ -e \"\${RELEASE}/backend\"
  cd \"\${RELEASE}\"
  sudo -u antibagu bash -lc \
    'set -a; source /etc/anti-bagu/anti-bagu.env; set +a; .venv/bin/alembic -c backend/alembic.ini upgrade head'

  install -m 0644 \"\${RELEASE}/deploy/systemd/anti-bagu.service\" \
    /etc/systemd/system/anti-bagu.service
  install -m 0644 \"\${RELEASE}/deploy/nginx/anti-bagu.conf\" \
    /etc/nginx/sites-available/anti-bagu
  ln -sfn /etc/nginx/sites-available/anti-bagu /etc/nginx/sites-enabled/anti-bagu
  nginx -t
  systemctl daemon-reload

  if [[ -L \"\${CURRENT}\" ]]; then
    PREVIOUS_TARGET=\"\$(readlink -f \"\${CURRENT}\")\"
  elif [[ -d \"\${CURRENT}\" ]]; then
    PREVIOUS_TARGET=\"\${RELEASE_ROOT}/legacy-${STAMP}\"
    mv \"\${CURRENT}\" \"\${PREVIOUS_TARGET}\"
  fi

  rm -f -- \"\${CURRENT}.new\"
  ln -s \"\${RELEASE}\" \"\${CURRENT}.new\"
  mv -Tf \"\${CURRENT}.new\" \"\${CURRENT}\"

  rollback() {
    systemctl stop anti-bagu || true
    rm -f -- \"\${CURRENT}\"
    if [[ -n \"\${PREVIOUS_TARGET}\" && -e \"\${PREVIOUS_TARGET}\" ]]; then
      ln -s \"\${PREVIOUS_TARGET}\" \"\${CURRENT}\"
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
