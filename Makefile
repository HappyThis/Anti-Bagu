PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: bootstrap bootstrap-backend bootstrap-web dev-backend dev-web dev-capture test test-backend test-swift build-web build-aec3 build-agent package-agent check

bootstrap: bootstrap-backend bootstrap-web

bootstrap-backend:
	$(PIP) install -e 'backend[test,lint]'

bootstrap-web:
	npm --prefix apps/web install

dev-backend:
	$(PYTHON) -m uvicorn anti_bagu.main:app --reload --host 127.0.0.1 --port 8765

dev-web:
	npm --prefix apps/web run dev

dev-capture:
	swift run --package-path apps/capture-macos anti-bagu-agent start

test: test-backend test-swift

test-backend:
	$(PYTHON) -m pytest -q backend/tests

test-swift: build-aec3
	swift test --package-path apps/capture-macos

build-web:
	npm --prefix apps/web run build

build-aec3:
	scripts/build-aec3-macos.sh

build-agent: build-aec3
	swift build -c release --package-path apps/capture-macos --product anti-bagu-agent

package-agent: build-agent
	mkdir -p apps/web/dist/downloads
	mkdir -p apps/capture-macos/.build/agent-package
	cp apps/capture-macos/.build/release/anti-bagu-agent apps/capture-macos/.build/agent-package/anti-bagu-agent
	cp apps/capture-macos/NativeAEC3/.build/WEBRTC-LICENSE.txt apps/capture-macos/NativeAEC3/.build/ABSEIL-LICENSE.txt apps/capture-macos/.build/agent-package/
	cp apps/capture-macos/Packaging/README.txt apps/capture-macos/.build/agent-package/
	chmod +x apps/capture-macos/.build/agent-package/anti-bagu-agent
	codesign --force --sign - apps/capture-macos/.build/agent-package/anti-bagu-agent
	tar -czf apps/web/dist/downloads/anti-bagu-agent-macos-arm64.tar.gz -C apps/capture-macos/.build/agent-package anti-bagu-agent README.txt WEBRTC-LICENSE.txt ABSEIL-LICENSE.txt
	shasum -a 256 apps/web/dist/downloads/anti-bagu-agent-macos-arm64.tar.gz > apps/web/dist/downloads/anti-bagu-agent-macos-arm64.tar.gz.sha256

check: test build-web
	$(PYTHON) -m ruff check backend/src backend/tests
	$(PYTHON) -m py_compile $$(rg --files backend/src backend/tests -g '*.py')
	git diff --check
