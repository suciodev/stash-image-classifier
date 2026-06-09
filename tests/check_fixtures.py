"""Quick accuracy check against fixture images. Run with: uv run python -m tests.check_fixtures"""
from pathlib import Path
from src.classifier import ImageClassifier
from src.nsfw_classifier import NsfwClassifier

# ── Person detection ──────────────────────────────────────────────────────────

clf = ImageClassifier()
base = Path("tests/fixtures/person_detection")

total = correct = 0

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _images(directory: Path):
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)


for label in ("include", "exclude"):
    expect_person = label == "include"
    print(f"\n--- {label.upper()} (expect has_person={expect_person}) ---")
    for img in _images(base / label):
        result = clf.has_person(str(img))
        ok = result == expect_person
        status = "OK   " if ok else "WRONG"
        print(f"  [{status}] has_person={result}  {img.name[:70]}")
        total += 1
        correct += ok

print(f"\nPerson result: {correct}/{total} correct ({100*correct//total}%)")

# ── NSFW detection ────────────────────────────────────────────────────────────

nsfw_clf = NsfwClassifier()
nsfw_base = Path("tests/fixtures/nsfw")

nsfw_total = nsfw_correct = 0

# Subdirs: explicit/, revealing/, suggestive/ → expect those tags
# Subdirs: clean/ → expect empty list
for label in ("explicit", "revealing", "suggestive", "clean"):
    fixture_dir = nsfw_base / label
    if not fixture_dir.exists():
        continue
    expect_tag = label if label != "clean" else None
    print(f"\n--- NSFW {label.upper()} (expect tag={expect_tag!r}) ---")
    for img in _images(fixture_dir):
        tags = nsfw_clf.classify(str(img))
        ok = (expect_tag in tags) if expect_tag else (tags == [])
        status = "OK   " if ok else "WRONG"
        print(f"  [{status}] tags={tags or '(none)'}  {img.name[:60]}")
        nsfw_total += 1
        nsfw_correct += ok

if nsfw_total:
    print(f"\nNSFW result: {nsfw_correct}/{nsfw_total} correct ({100*nsfw_correct//nsfw_total}%)")
else:
    print("\nNSFW result: no fixtures found — add images to tests/fixtures/nsfw/{explicit,revealing,suggestive,clean}/")
