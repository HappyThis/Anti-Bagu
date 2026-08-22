#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-anti-bagu}"
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

BRANCH="$(git branch --show-current)"
COMMIT="$(git rev-parse HEAD)"
REPOSITORY_URL="$(git remote get-url origin)"

if [[ -z "$BRANCH" ]]; then
  echo "拒绝部署：当前处于 detached HEAD，请先切换到需要发布的分支。" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "拒绝部署：工作区存在未提交修改。请先提交，确保线上版本对应唯一 commit。" >&2
  exit 1
fi

REMOTE_COMMIT="$(git ls-remote origin "refs/heads/$BRANCH" | awk 'NR == 1 { print $1 }')"
if [[ "$REMOTE_COMMIT" != "$COMMIT" ]]; then
  echo "拒绝部署：origin/$BRANCH 不是当前 commit $COMMIT，请先推送代码。" >&2
  exit 1
fi

echo "准备发布 $COMMIT（$BRANCH）"
npm --prefix apps/web run build
make package-agent

ARTIFACT="$(mktemp -t anti-bagu-web)"
trap 'unlink "$ARTIFACT" 2>/dev/null || true' EXIT
tar -czf "$ARTIFACT" -C apps/web dist
ARTIFACT_SHA256="$(shasum -a 256 "$ARTIFACT" | awk '{ print $1 }')"
REMOTE_ARTIFACT="/tmp/anti-bagu-web-$COMMIT.tar.gz"

scp "$ARTIFACT" "$TARGET:$REMOTE_ARTIFACT"
ssh "$TARGET" bash -s -- \
  "$REPOSITORY_URL" \
  "$COMMIT" \
  "$ARTIFACT_SHA256" \
  < "$ROOT_DIR/deploy/scripts/install-git-release.sh"

echo "发布完成：$COMMIT"
