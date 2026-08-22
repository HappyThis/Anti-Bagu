#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="$ROOT_DIR/.runtime/aec3-native"
TOOLS_DIR="$CACHE_DIR/tools"
SOURCE_DIR="$CACHE_DIR/source/webrtc-audio-processing-2.1"
BUILD_DIR="$CACHE_DIR/build-static-macos13"
OUTPUT_DIR="$ROOT_DIR/apps/capture-macos/NativeAEC3/.build"
ARCHIVE="$CACHE_DIR/source/webrtc-audio-processing-2.1.tar.xz"
ARCHIVE_URL="https://gstreamer.freedesktop.org/src/mirror/webrtc-audio-processing/webrtc-audio-processing-2.1.tar.xz"
ARCHIVE_SHA256="ae9302824b2038d394f10213cab05312c564a038434269f11dbf68f511f9f9fe"

mkdir -p "$CACHE_DIR/source" "$OUTPUT_DIR"
export MACOSX_DEPLOYMENT_TARGET=13.0

if [[ ! -f "$ARCHIVE" ]]; then
  curl -fL --retry 3 -o "$ARCHIVE" "$ARCHIVE_URL"
fi
echo "$ARCHIVE_SHA256  $ARCHIVE" | shasum -a 256 --check --status

if [[ ! -d "$SOURCE_DIR" ]]; then
  tar -xJf "$ARCHIVE" -C "$CACHE_DIR/source"
fi

if [[ ! -x "$TOOLS_DIR/bin/meson" || ! -x "$TOOLS_DIR/bin/ninja" ]]; then
  python3 -m venv "$TOOLS_DIR"
  "$TOOLS_DIR/bin/pip" install "meson>=1.4,<2" "ninja>=1.11,<2"
fi
export PATH="$TOOLS_DIR/bin:$PATH"

if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
  meson setup "$BUILD_DIR" "$SOURCE_DIR" \
    --wrap-mode=forcefallback \
    -Ddefault_library=static \
    -Dneon=enabled \
    -Dinline-sse=false
fi
meson compile -C "$BUILD_DIR"

APM_LIBRARY="$BUILD_DIR/webrtc/modules/audio_processing/libwebrtc-audio-processing-2.a"
BRIDGE_OBJECT="$CACHE_DIR/aec3_bridge.o"
STATIC_LIBRARY="$OUTPUT_DIR/libanti-bagu-aec3.a"

clang++ -std=c++20 -O2 -c \
  "$ROOT_DIR/apps/capture-macos/NativeAEC3/aec3_bridge.cpp" \
  -I "$SOURCE_DIR/webrtc" \
  -I "$SOURCE_DIR/subprojects/abseil-cpp-20240722.0" \
  -o "$BRIDGE_OBJECT"

/usr/bin/libtool -static -o "$STATIC_LIBRARY" "$BRIDGE_OBJECT" "$APM_LIBRARY"
cp "$SOURCE_DIR/COPYING" "$OUTPUT_DIR/WEBRTC-LICENSE.txt"
cp "$SOURCE_DIR/subprojects/abseil-cpp-20240722.0/LICENSE" "$OUTPUT_DIR/ABSEIL-LICENSE.txt"

echo "AEC3 static library built in $OUTPUT_DIR"
