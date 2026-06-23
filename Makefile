DEV_PLUGIN_DIR   = dev-infra/stash-config/plugins/stash-image-classifier
DEV_SCRAPER_DIR  = dev-infra/stash-config/scrapers/stash-image-classifier
PROD_PLUGIN_DIR  = /mnt/b/SteamLibrary/steamapps/shadercache/242069/O/stashdb/stash-common/plugins/stash-image-classifier
PROD_SCRAPER_DIR = /mnt/b/SteamLibrary/steamapps/shadercache/242069/O/stashdb/stash-common/scrapers/stash-image-classifier

# Files/dirs to exclude when syncing plugin source
RSYNC_FLAGS = -av --delete \
	--exclude='.*' \
	--exclude='*.pyc' \
	--exclude='__pycache__/' \
	--exclude='tests/' \
	--exclude='scrapers/' \
	--exclude='pyproject.toml' \
	--exclude='uv.lock' \
	--exclude='Dockerfile' \
	--exclude='docker-compose.yml' \
	--exclude='CLAUDE.md' \
	--exclude='Makefile' \
	--exclude='dev-infra/' \
	--exclude='debug_out/' \
	--exclude='docs/' \
	--exclude='yolov8n.pt' \
	--exclude='640m.onnx'

.PHONY: test check-fixtures test-scraper-dev \
        deploy-dev deploy-scraper-dev start-dev stop-dev logs-dev rebuild-dev \
        deploy deploy-scraper deploy-model deploy-all

# ── local tests ───────────────────────────────────────────────────────────────

test:
	uv run pytest -v

check-fixtures:
	uv run python -m tests.check_fixtures

# Run the imageByFragment scraper end-to-end via the Stash GraphQL API.
# Requires: dev container running (make start-dev) with fixture images scanned.
test-scraper-dev:
	uv run python -m tests.test_scraper_e2e

# ── dev stash instance (safe sandbox, port 9995) ──────────────────────────────

deploy-dev:
	mkdir -p "$(DEV_PLUGIN_DIR)/src"
	rsync $(RSYNC_FLAGS) ./ "$(DEV_PLUGIN_DIR)/"
	cp yolov8n.pt "$(DEV_PLUGIN_DIR)/yolov8n.pt"
	cp 640m.onnx "$(DEV_PLUGIN_DIR)/640m.onnx"
	@echo "Plugin deployed → $(DEV_PLUGIN_DIR)"

deploy-scraper-dev:
	mkdir -p "$(DEV_SCRAPER_DIR)"
	cp scrapers/stash-image-classifier.yml "$(DEV_SCRAPER_DIR)/"
	cp scrapers/classify.py "$(DEV_SCRAPER_DIR)/"
	@echo "Scraper deployed → $(DEV_SCRAPER_DIR)"

# Builds the dev image (first time is slow — downloads torch ~1 GB) then starts stash.
# After first build, subsequent starts skip --build unless you run rebuild-dev.
start-dev: deploy-dev deploy-scraper-dev
	docker compose -f dev-infra/docker-compose.yml up -d --build
	@echo "Stash dev running at http://localhost:9995"

stop-dev:
	docker compose -f dev-infra/docker-compose.yml down

logs-dev:
	docker compose -f dev-infra/docker-compose.yml logs -f stash-dev

# Force a clean image rebuild (e.g. after changing dev-infra/Dockerfile)
rebuild-dev:
	docker compose -f dev-infra/docker-compose.yml build --no-cache

# ── production deploy ─────────────────────────────────────────────────────────
# Only run when you're ready to push to live stash-sc/hc/pro.
# Requires rebuilding stash-git on the Windows side after the first time:
#   docker build -t stash-git B:/SteamLibrary/steamapps/shadercache/242069/O/stashdb/

deploy:
	mkdir -p "$(PROD_PLUGIN_DIR)/src"
	rsync $(RSYNC_FLAGS) ./ "$(PROD_PLUGIN_DIR)/"
	@echo "Plugin deployed → $(PROD_PLUGIN_DIR)"

deploy-scraper:
	mkdir -p "$(PROD_SCRAPER_DIR)"
	cp scrapers/stash-image-classifier.yml "$(PROD_SCRAPER_DIR)/"
	cp scrapers/classify.py "$(PROD_SCRAPER_DIR)/"
	@echo "Scraper deployed → $(PROD_SCRAPER_DIR)"

deploy-model: deploy
	cp yolov8n.pt "$(PROD_PLUGIN_DIR)/yolov8n.pt"
	cp 640m.onnx "$(PROD_PLUGIN_DIR)/640m.onnx"
	@echo "Model deployed → $(PROD_PLUGIN_DIR)"

deploy-all: deploy-model deploy-scraper
