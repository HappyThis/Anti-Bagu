#!/bin/bash
set -e
PACKAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$PACKAGE_DIR/anti-bagu-agent"
exec "$PACKAGE_DIR/anti-bagu-agent"
