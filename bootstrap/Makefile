PACKAGE     := r2bewi
VERSION     := 0.1.0
ARCH        := amd64

PYZ         := dist/r2bewi.pyz
BINARY      := dist/r2bewi
DEB         := dist/$(PACKAGE)_$(VERSION)_$(ARCH).deb
STUB        := src/system/debian/packaging/launcher.stub.sh
PY_SRC      := $(shell find src -type f -name '*.py')
DEFAULTS_SRC := $(shell find src -path '*/defaults/*' -type f)

DEB_ROOT    := dist/deb_root


.PHONY: build deb lint test test-dev clean show-packages

build: $(BINARY)

$(BINARY): $(STUB) $(PYZ)
	@mkdir -p dist
	@cat $(STUB) > $(BINARY)
	@base64 -w 0 $(PYZ) >> $(BINARY)
	@printf '\n' >> $(BINARY)
	@chmod +x $(BINARY)
	@echo "Built: $(BINARY) ($$(wc -c < $(BINARY)) bytes)"

$(PYZ): $(PY_SRC) $(DEFAULTS_SRC)
	@mkdir -p dist dist/_pyz_staging
	@cp -r src dist/_pyz_staging/
	@echo "from src.cli import main; main()" > dist/_pyz_staging/__main__.py
	@python3 -m zipapp dist/_pyz_staging --output $(PYZ) \
		--python "/usr/bin/env python3" --compress
	@rm -rf dist/_pyz_staging

deb: $(DEB)

$(DEB): $(BINARY)
	@echo "=== Construction paquet .deb ==="
	@rm -rf $(DEB_ROOT)
	@mkdir -p $(DEB_ROOT)/DEBIAN
	@mkdir -p $(DEB_ROOT)/usr/bin
	@mkdir -p $(DEB_ROOT)/usr/lib/r2bewi
	# Fichiers DEBIAN
	@cp src/system/debian/packaging/DEBIAN/control $(DEB_ROOT)/DEBIAN/control
	@cp src/system/debian/packaging/DEBIAN/postinst $(DEB_ROOT)/DEBIAN/postinst
	@cp src/system/debian/packaging/DEBIAN/prerm    $(DEB_ROOT)/DEBIAN/prerm
	@chmod 755 $(DEB_ROOT)/DEBIAN/postinst $(DEB_ROOT)/DEBIAN/prerm
	# Binaire + zipapp
	@cp $(BINARY) $(DEB_ROOT)/usr/bin/r2bewi
	@chmod 755 $(DEB_ROOT)/usr/bin/r2bewi
	@cp $(PYZ) $(DEB_ROOT)/usr/lib/r2bewi/r2bewi.pyz
	# Build
	@dpkg-deb --build --root-owner-group $(DEB_ROOT) $(DEB)
	@echo "Paquet : $(DEB)"

lint:
	@python3 -m py_compile $(PY_SRC)
	@echo "Syntax OK"

test:
	@python3 -m pytest -v

test-dev:
	@pip install -q -r requirements-dev.txt
	@python3 -m pytest -v

show-packages:
	@echo "=== Paquets installés par r2bewi deploy (par composant) ==="
	@python3 -c "\
import yaml, pathlib; \
[print(f'  {f.parent.name:<12} {yaml.safe_load(f.read_text()).get(\"packages\", [])}') \
 for f in sorted(pathlib.Path('src/components').glob('*/component.yaml'))]"
	@echo ""
	@echo "=== .deb Depends (CLI uniquement) ==="
	@grep '^Depends:' src/system/debian/packaging/DEBIAN/control

clean:
	@rm -rf dist/ __pycache__ src/__pycache__
	@find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
