PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: bootstrap bootstrap-backend bootstrap-web dev-backend dev-web dev-capture test test-backend test-swift build-web build-agent package-agent check

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

test-swift:
	swift test --package-path apps/capture-macos

build-web:
	npm --prefix apps/web run build

build-agent:
	swift build -c release --package-path apps/capture-macos --product anti-bagu-agent

package-agent: build-agent
	mkdir -p apps/web/dist/downloads
	tar -czf apps/web/dist/downloads/anti-bagu-agent-macos-arm64.tar.gz -C apps/capture-macos/.build/release anti-bagu-agent
	shasum -a 256 apps/web/dist/downloads/anti-bagu-agent-macos-arm64.tar.gz > apps/web/dist/downloads/anti-bagu-agent-macos-arm64.tar.gz.sha256

check: test build-web
	$(PYTHON) -m ruff check backend/src backend/tests
	$(PYTHON) -m py_compile $$(rg --files backend/src backend/tests -g '*.py')
	git diff --check
