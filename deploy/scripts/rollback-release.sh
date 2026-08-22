#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-anti-bagu}"
COMMIT="${2:-}"

if [[ ! "$COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "用法：deploy/scripts/rollback-release.sh [SSH目标] <完整commit>" >&2
  exit 1
fi

ssh "$TARGET" bash -s -- "$COMMIT" <<'REMOTE'
set -euo pipefail

COMMIT="$1"
DEPLOY_ROOT=/opt/anti-bagu-deploy
RELEASE="$DEPLOY_ROOT/releases/$COMMIT"
APP_LINK=/opt/anti-bagu
NEXT_LINK="$DEPLOY_ROOT/.next-current"

if [[ ! -f "$RELEASE/.release-ready" ]]; then
  echo "找不到可回滚版本：$COMMIT" >&2
  exit 1
fi

PREVIOUS_TARGET="$(readlink -f "$APP_LINK")"
unlink "$NEXT_LINK" 2>/dev/null || true
ln -s "$RELEASE" "$NEXT_LINK"
mv -Tf "$NEXT_LINK" "$APP_LINK"

if ! systemctl restart anti-bagu; then
  unlink "$NEXT_LINK" 2>/dev/null || true
  ln -s "$PREVIOUS_TARGET" "$NEXT_LINK"
  mv -Tf "$NEXT_LINK" "$APP_LINK"
  systemctl restart anti-bagu
  echo "回滚版本无法启动，已恢复原版本。" >&2
  exit 1
fi

for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8765/health >/dev/null; then
    echo "已回滚到：$COMMIT"
    exit 0
  fi
  sleep 0.5
done

unlink "$NEXT_LINK" 2>/dev/null || true
ln -s "$PREVIOUS_TARGET" "$NEXT_LINK"
mv -Tf "$NEXT_LINK" "$APP_LINK"
systemctl restart anti-bagu
echo "回滚版本健康检查失败，已恢复原版本。" >&2
exit 1
REMOTE
