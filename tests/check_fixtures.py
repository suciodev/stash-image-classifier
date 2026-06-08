"""Quick accuracy check against fixture images. Run with: uv run python tests/check_fixtures.py"""
from src.classifier import ImageClassifier
from pathlib import Path

clf = ImageClassifier()
base = Path("tests/fixtures/person_detection")

total = correct = 0

for label in ("include", "exclude"):
    expect_person = label == "include"
    print(f"\n--- {label.upper()} (expect has_person={expect_person}) ---")
    for img in sorted((base / label).iterdir()):
        result = clf.has_person(str(img))
        ok = result == expect_person
        status = "OK   " if ok else "WRONG"
        print(f"  [{status}] has_person={result}  {img.name[:70]}")
        total += 1
        correct += ok

print(f"\nResult: {correct}/{total} correct ({100*correct//total}%)")
