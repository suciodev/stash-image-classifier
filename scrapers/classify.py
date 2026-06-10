#!/usr/bin/env python3
"""
Per-image scraper entry point for Stash.

Stash invokes this as an imageByFragment scraper: it sends the current image
data as JSON on stdin, and expects a JSON object with updated fields on stdout.

Pipeline (priority order):
1. NSFW detection — runs unconditionally; catches explicit images YOLO misses.
2. Person detection — if no person and no NSFW, return "exclude".
3. Clothing detection — runs when person is present; NSFW and clothing tags
   are not mutually exclusive (a lingerie image can receive both).
"""
import contextlib
import json
import os
import sys

import requests

# Insert the sibling plugin directory so src.* imports resolve.
# Container layout:
#   scrapers/stash-image-classifier/classify.py  (this file)
#   plugins/stash-image-classifier/src/
_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "plugins", "stash-image-classifier",
)
sys.path.insert(0, _PLUGIN_DIR)


@contextlib.contextmanager
def _suppress_stdout():
    """Redirect stdout → stderr for the duration of the block.

    onnxruntime (NudeNet) and ultralytics both print startup noise at import
    and at construction time.  Any stray byte on stdout corrupts the JSON
    that Stash reads from the scraper process.
    """
    old = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old


with _suppress_stdout():
    from src.classifier import ImageClassifier          # noqa: E402
    from src.nsfw_classifier import NsfwClassifier      # noqa: E402
    from src.clothing_classifier import ClothingClassifier  # noqa: E402
    _person_clf = ImageClassifier()
    _nsfw_clf = NsfwClassifier()
    _clothing_clf = ClothingClassifier()


_STASH_PORT = os.environ.get("STASH_PORT", "9999")
_STASH_URL = f"http://localhost:{_STASH_PORT}/graphql"


def _get_path_from_fragment(data: dict) -> str | None:
    """Extract the image file path from the Stash fragment payload (if present).

    In practice the imageByFragment fragment never includes file paths, so this
    almost always returns None and the caller falls through to _lookup_path_by_id.
    Kept as a fast-path guard for forward compatibility.
    """
    for f in data.get("files", []):
        if p := f.get("path"):
            return p
    for f in data.get("visual_files", []):
        if p := f.get("path"):
            return p
    return None


def _lookup_path_by_id(image_id: str) -> str | None:
    """Call the local Stash API to get the file path for an image ID."""
    query = """
        query FindImage($id: ID!) {
            findImage(id: $id) {
                visual_files { ... on ImageFile { path } }
            }
        }
    """
    try:
        resp = requests.post(_STASH_URL, json={"query": query, "variables": {"id": image_id}}, timeout=10)
        img = resp.json().get("data", {}).get("findImage") or {}
        for f in img.get("visual_files", []):
            if p := f.get("path"):
                return p
    except Exception:
        pass
    return None


def _classify_image(path: str) -> dict:
    nsfw_tags = _nsfw_clf.classify(path)
    has_person = _person_clf.has_person(path)
    if not has_person and not nsfw_tags:
        return {"tags": [{"name": "exclude"}]}
    clothing_tags = _clothing_clf.classify(path) if has_person else []
    all_tags = nsfw_tags + clothing_tags
    return {"tags": [{"name": t} for t in all_tags]} if all_tags else {}


def main():
    data = json.loads(sys.stdin.read())

    path = _get_path_from_fragment(data)
    if not path and data.get("id"):
        path = _lookup_path_by_id(data["id"])

    if path and not os.path.isabs(path):
        path = "/" + path
    if not path or not os.path.isfile(path):
        print(json.dumps({}))
        return

    print(json.dumps(_classify_image(path)))


if __name__ == "__main__":
    main()
