# Clothing Classifier — Design Spec

**Date:** 2026-06-23  
**Status:** Approved  
**Branch:** `feature/clothing-classifier`

## Goal

Add a `ClothingClassifier` that tags images of people with their clothing category. The classifier runs only when a person is detected, produces one of four tags (`swimwear`, `lingerie`, `activewear`, `dress`), and applies alongside (not instead of) NSFW tags.

## Tag Mapping

Fixtures exist for 5 categories; similar ones are grouped into 4 output tags:

| Fixtures | Output tag |
|---|---|
| `bikini/`, `swimwear/` | `swimwear` |
| `lingerie/` | `lingerie` |
| `sportswear/` | `activewear` |
| `dress/` | `dress` |

A 5th CLIP prompt ("everyday clothes") acts as a catch-all that produces no tag.

## Approach

CLIP zero-shot classification via `openai/clip-vit-base-patch32` (HuggingFace `transformers`). No training required — categories are just prompt strings. Model downloads to `~/.cache/huggingface` on first run (~600 MB). `torch` is already a dependency; `transformers>=4.30.0` is the only new package.

Prompt wording is the primary tuning surface. The fixture accuracy check (`tests/check_fixtures.py`) provides fast iteration feedback before any threshold is touched.

## Pipeline

```
has_person    = YOLO(path)
nsfw_tags     = NsfwClassifier(path)          # always runs
clothing_tags = ClothingClassifier(path)       # only when has_person=True

combined = nsfw_tags + clothing_tags
if combined  → return combined                 # e.g. ["suggestive", "swimwear"]
if not has_person → return ["exclude"]
return []                                      # person present, clean
```

NSFW and clothing tags are independent axes — an image can receive both (e.g. a bikini image that also triggers `suggestive`).

## Components

### `src/clothing_classifier.py` (new)

```python
_PROMPTS = [
    "a person wearing a bikini or swimwear",
    "a person wearing lingerie or underwear",
    "a person wearing sportswear or activewear",
    "a person wearing a dress",
    "a person wearing everyday clothes",   # catch-all → no tag
]

_TAG_MAP = {0: "swimwear", 1: "lingerie", 2: "activewear", 3: "dress", 4: None}
_THRESHOLD = 0.5
```

`classify(path: str) -> list[str]`: loads image, runs CLIP, returns `[tag]` if softmax winner ≥ threshold, else `[]`. Returns `[]` on missing file or model exception.

Model loaded once at construction. `CLIPModel` and `CLIPProcessor` from `transformers`.

### `main.py` changes

- `_CLASSIFIER_TAGS` gains `"swimwear"`, `"lingerie"`, `"activewear"`, `"dress"`
- `_classify_image` gains `clothing_classifier` as 3rd positional parameter; removes the NSFW early-return so both tag sets accumulate
- `main()` instantiates `ClothingClassifier()`
- `run_classify` and `run_hook` pass it through to `_classify_image`

### `scrapers/classify.py` changes

- Import `ClothingClassifier` from sibling `src/`
- Import `_classify_image` from `main` (removes duplicated logic — this wiring is a natural moment to close that gap)
- Instantiate `ClothingClassifier()` at module level
- Pass it to `_classify_image`

### `pyproject.toml`

Add `transformers>=4.30.0` to `[project.dependencies]`.

## Testing

### Unit tests — `tests/test_clothing_classifier.py` (new)

Mock `CLIPModel` and `CLIPProcessor` entirely (no network, no download). Cases:
- Returns correct tag when softmax winner ≥ threshold
- Returns `[]` when best probability < threshold
- Returns `[]` for missing file
- Returns `[]` when neutral prompt (index 4) wins
- Returns `[]` on model exception

### `_classify_image` tests — `tests/test_main.py` (extend)

Add `clothing_classifier` mock to `_make_classifiers`. New cases:
- Person + no NSFW + clothing match → clothing tag
- Person + NSFW + clothing match → both tag sets combined
- No person + clothing match → `exclude` returned (gating enforced)
- Person + no NSFW + no clothing match → `[]`

### Fixture accuracy check — `tests/check_fixtures.py` (extend)

New loop over `tests/fixtures/clothing/` (94 images across 5 directories). Reports per-category accuracy. Run manually with `uv run python -m tests.check_fixtures`. Not part of `pytest`.

## File Map

| File | Change |
|---|---|
| `src/clothing_classifier.py` | New |
| `main.py` | Extend `_CLASSIFIER_TAGS`, `_classify_image`, `main()`, `run_classify`, `run_hook` |
| `scrapers/classify.py` | Import `ClothingClassifier`, import `_classify_image` from `main` |
| `tests/test_clothing_classifier.py` | New |
| `tests/test_main.py` | Extend with clothing mock + 4 new `_classify_image` cases |
| `tests/check_fixtures.py` | Extend with clothing accuracy loop |
| `pyproject.toml` | Add `transformers>=4.30.0` |
| `stash-image-classifier.yml` | Bump version |

## Constraints

- Python 3.9+ syntax (no 3.10+ union types)
- No AI API calls — local inference only
- Model download on first use (HuggingFace cache); no bundling
- Prompt wording tuned against fixtures before threshold is adjusted
