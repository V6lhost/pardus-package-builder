VERSION = 1.0.0
PYTHON = python3
PIP = pip3

BUILD_DIR = debian/usr/share/pardus-package-builder
DEB_OUTPUT_DIR = output_deb
DEB_NAME = pardus-package-builder-$(VERSION).deb
SRC_DIR = src
REQS = requirements.txt

.PHONY: all build clean run update-control

all: build

update-control:
	@echo "[*] debian/DEBIAN/control version info is set $(VERSION)..."
	@if [ -f "debian/DEBIAN/control" ]; then \
		sed -i 's/^Version: .*/Version: $(VERSION)/' debian/DEBIAN/control; \
	else \
		echo "[-] Warning: debian/DEBIAN/control not found, skipping."; \
	fi

build: update-control
	@echo "[+] Building..."
	@mkdir -p $(BUILD_DIR)
	@if [ -d "src" ]; then cp -r src/ $(BUILD_DIR)/; fi
	@mkdir -p $(DEB_OUTPUT_DIR)
	@if [ -f "$(BUILD_DIR)/.gitkeep" ]; then rm "$(BUILD_DIR)/.gitkeep"; fi
	@if [ -d "dist/main" ]; then mv dist/main/* $(BUILD_DIR)/ && rmdir dist/main; fi
	dpkg-deb --root-owner-group --build debian $(DEB_OUTPUT_DIR)/$(DEB_NAME)
	@echo "[+] Build done! Output: $(DEB_OUTPUT_DIR)/$(DEB_NAME)"

run:
	@echo "[+] Running with system Python..."
	$(PYTHON) $(SRC_DIR)/main.py

clean:
	@echo "[-] Cleaning up..."
	@rm -rf build/ dist/ *.spec __pycache__ $(SRC_DIR)/__pycache__ $(DEB_OUTPUT_DIR)
	@rm -rf $(BUILD_DIR)/*
	@echo "[+] Done."