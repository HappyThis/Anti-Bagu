PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: bootstrap bootstrap-backend bootstrap-web dev-backend dev-web dev-capture test test-backend test-swift build-web check

bootstrap: bootstrap-backend bootstrap-web

bootstrap-backend:
	$(PIP) install -e 'backend[test]'

bootstrap-web:
	npm --prefix apps/web install

dev-backend:
	$(PYTHON) -m uvicorn anti_bagu.main:app --reload --host 127.0.0.1 --port 8765

dev-web:
	npm --prefix apps/web run dev

dev-capture:
	swift run --package-path apps/capture-macos anti-bagu-capture

test: test-backend test-swift

test-backend:
	$(PYTHON) -m pytest -q backend/tests

test-swift:
	swift test --package-path apps/capture-macos

build-web:
	npm --prefix apps/web run build

check: test build-web
	$(PYTHON) -m py_compile $$(rg --files backend/src backend/tests -g '*.py')
	git diff --check
