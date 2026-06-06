# stash-image-classifier

A [Stash](https://github.com/stashapp/stash) plugin that classifies images using local ML inference and auto-applies tags. The initial use case: tag images where no person is the main subject with an `exclude` label — useful for filtering Instagram media libraries.

All inference runs locally. No external AI API calls, no token costs.

## How it works

The plugin ships three integration points:

| Integration | How to use |
|---|---|
| **Bulk task** | Tasks panel → "Classify Images" — processes every image in the library |
| **Auto-hook** | Fires on `Image.Create.Post` — classifies each image as it is scanned |
| **Per-image scraper** | Image edit dialog → "Scrape with Image Classifier" — classifies one image on demand |

Detection uses YOLOv8n: an image is considered to have a person if YOLO returns at least one bounding box with ≥60% confidence that covers ≥5% of the image area. Images that don't meet this threshold are tagged `exclude`.

## Installation

1. Copy the plugin directory to your Stash plugins folder:
   ```
   <stash-config>/plugins/stash-image-classifier/
   ```
2. Copy the scraper directory to your Stash scrapers folder:
   ```
   <stash-config>/scrapers/stash-image-classifier/
   ```
3. Ensure `python` (3.9+) is on the path with `ultralytics`, `opencv-python-headless`, and `requests` installed.
4. The model file `yolov8n.pt` (~6 MB) must be present in the plugin directory for fully-offline use. If absent, ultralytics will attempt to download it on first run.
5. Reload plugins in Stash (Settings → Plugins → Reload).

## Development

See [CLAUDE.md](CLAUDE.md) for the full development guide, including:
- Local test commands
- Dev Stash sandbox setup (`make start-dev`, port 9995)
- Known platform issues (Alpine + PyTorch libgomp)
- GraphQL API reference

Quick start:
```bash
uv sync           # install deps
uv run pytest     # unit tests
make start-dev    # spin up isolated dev Stash on port 9995
```

## Known limitations

- **Swimmers / submerged bodies** — YOLO (trained on COCO) misses people lying horizontal or underwater.
- **Illustrations / artwork** — model trained on photographs; illustrated people not reliably detected.
- **Product shots with partial bodies** — a cropped hand or face in a product photo may trigger a false positive.

## License

MIT
