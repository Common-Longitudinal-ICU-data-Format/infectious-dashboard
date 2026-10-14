# Usage:
#   make setup    install Python + Node dependencies (once)
#   make export   read CLIF files named in config.yaml, write the dashboard JSON
#   make dev      start the dashboard at http://localhost:5173
#   make build    production build into app/dist (static, can be opened offline)
#   make test     check the export and chart-builder against the data
PY ?= python3

.PHONY: setup export dev build test

setup:
	$(PY) -m pip install -r requirements.txt
	cd app && npm install

export:
	$(PY) export/export.py --config config.yaml

dev:
	cd app && npm run dev

build:
	cd app && npm run build

test:
	$(PY) export/test_export.py
	cd app && npm test
