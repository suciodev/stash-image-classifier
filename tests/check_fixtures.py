"""Quick accuracy check against fixture images. Run with: uv run python -m tests.check_fixtures

Files prefixed with xfail_ are known model limitations: they are shown as [KNOWN]
when the model gets them wrong (expected), or [XPASS] when the model unexpectedly
gets them right. xfail_ files are excluded from the pass/fail score.
"""
from pathlib import Path
from src.classifier import ImageClassifier
from src.nsfw_classifier import NsfwClassifier

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_XFAIL_PREFIX = "xfail_"


def _images(directory: Path):
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)


# ── Person detection ──────────────────────────────────────────────────────────

clf = ImageClassifier()
base = Path("tests/fixtures/person_detection")

total = correct = 0

for label in ("include", "exclude"):
    expect_person = label == "include"
    print(f"\n--- {label.upper()} (expect has_person={expect_person}) ---")
    for img in _images(base / label):
        is_xfail = img.name.startswith(_XFAIL_PREFIX)
        result = clf.has_person(str(img))
        ok = result == expect_person
        if is_xfail:
            status = "XPASS" if ok else "KNOWN"
        else:
            status = "OK   " if ok else "WRONG"
            total += 1
            correct += ok
        print(f"  [{status}] has_person={result}  {img.name[:70]}")

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
        is_xfail = img.name.startswith(_XFAIL_PREFIX)
        tags = nsfw_clf.classify(str(img))
        ok = (expect_tag in tags) if expect_tag else (tags == [])
        if is_xfail:
            status = "XPASS" if ok else "KNOWN"
        else:
            status = "OK   " if ok else "WRONG"
            nsfw_total += 1
            nsfw_correct += ok
        print(f"  [{status}] tags={tags or '(none)'}  {img.name[:60]}")

if nsfw_total:
    print(f"\nNSFW result: {nsfw_correct}/{nsfw_total} correct ({100*nsfw_correct//nsfw_total}%)")
else:
    print("\nNSFW result: no fixtures found — add images to tests/fixtures/nsfw/{explicit,revealing,suggestive,clean}/")

# ── Clothing detection ────────────────────────────────────────────────────────

from src.clothing_classifier import ClothingClassifier  # noqa: E402

clothing_clf = ClothingClassifier()
clothing_base = Path("tests/fixtures/clothing")

clothing_total = clothing_correct = 0

# Subdirs: bikini/, swimwear/, lingerie/, sportswear/, dress/ → expect that tag
# Any dir named "clean" → expect empty list
for label in ("bikini", "swimwear", "lingerie", "sportswear", "dress", "clean"):
    fixture_dir = clothing_base / label
    if not fixture_dir.exists():
        continue
    expect_tag = label if label != "clean" else None
    print(f"\n--- CLOTHING {label.upper()} (expect tag={expect_tag!r}) ---")
    for img in _images(fixture_dir):
        is_xfail = img.name.startswith(_XFAIL_PREFIX)
        tags = clothing_clf.classify(str(img))
        ok = (expect_tag in tags) if expect_tag else (tags == [])
        if is_xfail:
            status = "XPASS" if ok else "KNOWN"
        else:
            status = "OK   " if ok else "WRONG"
            clothing_total += 1
            clothing_correct += ok
        print(f"  [{status}] tags={tags or '(none)'}  {img.name[:60]}")

if clothing_total:
    print(f"\nClothing result: {clothing_correct}/{clothing_total} correct ({100*clothing_correct//clothing_total}%)")
else:
    print("\nClothing result: no fixtures found — add images to tests/fixtures/clothing/{bikini,swimwear,lingerie,sportswear,dress}/")
