#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_URL="${1:?repository URL is required}"
COMMIT="${2:?commit is required}"
ARTIFACT_SHA256="${3:?artifact SHA-256 is required}"

if [[ ! "$COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "非法 commit：$COMMIT" >&2
  exit 1
fi
if [[ ! "$ARTIFACT_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "非法构建产物摘要。" >&2
  exit 1
fi

DEPLOY_ROOT=/opt/anti-bagu-deploy
REPOSITORY="$DEPLOY_ROOT/repository"
RELEASES="$DEPLOY_ROOT/releases"
STAGING_ROOT="$DEPLOY_ROOT/staging"
FAILED="$DEPLOY_ROOT/failed"
LEGACY="$DEPLOY_ROOT/legacy"
ARTIFACTS="$DEPLOY_ROOT/artifacts"
RELEASE="$RELEASES/$COMMIT"
STAGING="$STAGING_ROOT/$COMMIT-$$"
APP_LINK=/opt/anti-bagu
UPLOADED_ARTIFACT="/tmp/anti-bagu-web-$COMMIT.tar.gz"
STORED_ARTIFACT="$ARTIFACTS/web-$COMMIT.tar.gz"

cleanup() {
  local exit_status=$?
  unlink "$UPLOADED_ARTIFACT" 2>/dev/null || true
  if [[ $exit_status -ne 0 ]]; then
    local failed_at
    failed_at="$(date -u +%Y%m%dT%H%M%SZ)"
    if [[ -d "$STAGING" ]]; then
      mv "$STAGING" "$FAILED/$COMMIT-$failed_at"
    elif [[ -d "$RELEASE" && ! -f "$RELEASE/.release-ready" ]]; then
      mv "$RELEASE" "$FAILED/$COMMIT-$failed_at"
    fi
  fi
}
trap cleanup EXIT

if [[ ! -f "$UPLOADED_ARTIFACT" ]]; then
  echo "找不到构建产物：$UPLOADED_ARTIFACT" >&2
  exit 1
fi
echo "$ARTIFACT_SHA256  $UPLOADED_ARTIFACT" | sha256sum --check --status

install -d -m 0755 -o antibagu -g antibagu \
  "$DEPLOY_ROOT" "$RELEASES" "$STAGING_ROOT" "$FAILED" "$LEGACY" "$ARTIFACTS"

if [[ ! -d "$REPOSITORY/.git" ]]; then
  sudo -u antibagu git clone --filter=blob:none --no-checkout \
    "$REPOSITORY_URL" "$REPOSITORY"
else
  CONFIGURED_URL="$(sudo -u antibagu git -C "$REPOSITORY" remote get-url origin)"
  if [[ "$CONFIGURED_URL" != "$REPOSITORY_URL" ]]; then
    echo "服务器仓库地址不一致：$CONFIGURED_URL" >&2
    exit 1
  fi
fi

sudo -u antibagu git -C "$REPOSITORY" fetch --prune origin
sudo -u antibagu git -C "$REPOSITORY" cat-file -e "$COMMIT^{commit}"

if [[ -e "$RELEASE" ]]; then
  echo "版本已经存在：$RELEASE。请使用 rollback-release.sh 切换已有版本。" >&2
  exit 1
fi

install -d -m 0755 -o antibagu -g antibagu "$STAGING"
sudo -u antibagu git -C "$REPOSITORY" archive --format=tar "$COMMIT" \
  | sudo -u antibagu tar -xf - -C "$STAGING"

install -m 0644 -o antibagu -g antibagu "$UPLOADED_ARTIFACT" "$STORED_ARTIFACT"
sudo -u antibagu tar -xzf "$STORED_ARTIFACT" -C "$STAGING/apps/web"
mv "$STAGING" "$RELEASE"

sudo -u antibagu python3 -m venv "$RELEASE/.venv"
sudo -u antibagu "$RELEASE/.venv/bin/pip" install \
  -i https://mirrors.aliyun.com/pypi/simple/ \
  "$RELEASE/backend"

sudo -u antibagu bash -lc "
  set -euo pipefail
  cd '$RELEASE'
  set -a
  source /etc/anti-bagu/anti-bagu.env
  set +a
  .venv/bin/alembic -c backend/alembic.ini upgrade head
"

printf '%s\n' "$COMMIT" > "$RELEASE/.deploy-revision"
touch "$RELEASE/.release-ready"
chown antibagu:antibagu "$RELEASE/.deploy-revision" "$RELEASE/.release-ready"
nginx -t

PREVIOUS_TARGET=""
if [[ -L "$APP_LINK" ]]; then
  PREVIOUS_TARGET="$(readlink -f "$APP_LINK")"
elif [[ -d "$APP_LINK" ]]; then
  LEGACY_RELEASE="$LEGACY/pre-git-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$APP_LINK" "$LEGACY_RELEASE"
  PREVIOUS_TARGET="$LEGACY_RELEASE"
elif [[ -e "$APP_LINK" ]]; then
  echo "$APP_LINK 既不是目录也不是符号链接，拒绝覆盖。" >&2
  exit 1
fi

activate_release() {
  local target="$1"
  local next_link="$DEPLOY_ROOT/.next-current"
  unlink "$next_link" 2>/dev/null || true
  ln -s "$target" "$next_link"
  if [[ -L "$APP_LINK" ]]; then
    mv -Tf "$next_link" "$APP_LINK"
  elif [[ ! -e "$APP_LINK" ]]; then
    mv "$next_link" "$APP_LINK"
  else
    echo "无法切换 $APP_LINK" >&2
    return 1
  fi
}

wait_for_health() {
  local attempt
  for attempt in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8765/health >/dev/null; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

activate_release "$RELEASE"
if ! systemctl restart anti-bagu || ! wait_for_health; then
  echo "新版本启动失败，正在恢复上一版本。" >&2
  journalctl -u anti-bagu -n 40 --no-pager >&2 || true
  if [[ -n "$PREVIOUS_TARGET" && -d "$PREVIOUS_TARGET" ]]; then
    activate_release "$PREVIOUS_TARGET"
    systemctl restart anti-bagu
  fi
  exit 1
fi

systemctl reload nginx
echo "当前线上版本：$(cat "$APP_LINK/.deploy-revision")"
