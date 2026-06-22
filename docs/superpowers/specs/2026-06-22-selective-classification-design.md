# Selective Classification & Plugin Rename — Design Spec

**Date:** 2026-06-22
**Branch:** feature/selective-classification
**Version bump:** 0.3.0 → 0.4.0

## Problem

The bulk classification tasks process the entire image library (10s of thousands of images in production). There is no way to target a subset — e.g. a single gallery, studio, or recently imported folder — without running the full library scan.

## Solution

Add a marker-tag workflow: the user applies `percepttag:pending` to any images they want classified (via Stash's native bulk-select UI), then triggers a new "Classify Marked Images" task that processes only those images. After each image is processed, the marker is swapped to `percepttag:done`.

## Plugin Rename

- `name` in `stash-image-classifier.yml`: `Image Classifier` → `PerceptTag`
- `description` updated to reflect ML/computer-vision framing
- `version`: `0.3.0` → `0.4.0`
- Internal file names and repo name unchanged

## New Task Variant

Added to `stash-image-classifier.yml`:

```yaml
- name: Classify Marked Images
  description: >
    Classifies only images tagged with 'percepttag:pending'. Applies exclude/NSFW
    severity tags as normal, then swaps the marker to 'percepttag:done' regardless
    of outcome. Use Stash's bulk-select UI to mark images before running.
  defaultArgs:
    mode: classify
    batch_size: 50
    tagged_only: true
```

The three existing task variants (`Classify All Images`, `Classify Untagged Images`, `Recheck Exclude-Tagged Images`) are unchanged.

## StashClient Changes (`src/stash_client.py`)

Two new methods, existing methods untouched:

### `count_images_by_tag(tag_id: str) -> int`

Queries `findImages` with `ImageFilterType` tag filter (INCLUDES modifier), `per_page: 1`, returns `count`. Used for progress calculation in the selective path.

### `find_images_by_tag(tag_id: str, page: int, per_page: int) -> list[dict]`

Same filter with pagination. Returns the same dict shape as `find_images` (`id`, `path`, `tag_ids`).

## main.py Changes

`run_classify` gains a `tagged_only` code path (triggered when `args.get("tagged_only")` is true):

1. Resolve `percepttag:pending` and `percepttag:done` tag IDs upfront (created if missing).
2. Use `count_images_by_tag` / `find_images_by_tag` for iteration instead of the plain variants.
3. After classifying each image, remove `percepttag:pending` and add `percepttag:done` in the **same** `update_image_tags` call that applies classifier tags — one GraphQL mutation per image, no extra round trip.
4. The swap happens unconditionally: even if no classifier tags change, the marker is always moved to `done` so the user knows the image was processed.

`run_hook` and `scrapers/classify.py` are unchanged.

## Tag Lifecycle

```
User bulk-applies in Stash UI
        │
        ▼
percepttag:pending  ──── "Classify Marked Images" task ────►  percepttag:done
                                    │
                                    ▼
                         + exclude / explicit / revealing / suggestive
                           (as determined by classifiers)
```

## Testing

Two new unit tests (no new fixture images needed — StashClient is mocked):

- **`test_classify_marked_images`** — verifies that with `tagged_only=True`, only images with `percepttag:pending` are fetched, classifier tags are applied, and the marker is swapped to `percepttag:done` in a single `update_image_tags` call.
- **`test_classify_marked_images_no_change`** — verifies that an image requiring no classifier tag changes still has its marker swapped to `percepttag:done`.

## Out of Scope

- Gallery-level or studio-level marker tags (image-level is sufficient; Stash's bulk-select handles the "mark a whole gallery" workflow)
- Config-file-based filtering
- Scraper changes
