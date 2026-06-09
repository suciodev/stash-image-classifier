import pytest
from unittest.mock import patch, MagicMock
from src.nsfw_classifier import NsfwClassifier


def _det(label: str, score: float = 0.90) -> dict:
    return {"class": label, "score": score, "box": [0, 0, 100, 100]}


def _make_classifier(detections=None):
    mock_detector = MagicMock()
    mock_detector.detect.return_value = detections if detections is not None else []
    with patch("src.nsfw_classifier.NudeDetector", return_value=mock_detector):
        clf = NsfwClassifier()
    clf.detector = mock_detector
    return clf


def test_returns_empty_for_missing_file():
    clf = _make_classifier()
    assert clf.classify("/nonexistent/image.jpg") == []


def test_returns_empty_when_no_detections(tmp_path):
    img = tmp_path / "blank.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[])
    assert clf.classify(str(img)) == []


def test_returns_empty_when_all_below_threshold(tmp_path):
    img = tmp_path / "low.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("FEMALE_BREAST_EXPOSED", score=0.20)])
    assert clf.classify(str(img)) == []


def test_returns_explicit_for_exposed_breast(tmp_path):
    img = tmp_path / "explicit.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("FEMALE_BREAST_EXPOSED")])
    assert clf.classify(str(img)) == ["explicit"]


def test_returns_explicit_for_exposed_genitalia(tmp_path):
    img = tmp_path / "explicit2.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("MALE_GENITALIA_EXPOSED")])
    assert clf.classify(str(img)) == ["explicit"]


def test_returns_revealing_for_exposed_buttocks(tmp_path):
    img = tmp_path / "revealing.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("BUTTOCKS_EXPOSED")])
    assert clf.classify(str(img)) == ["revealing"]


def test_returns_suggestive_for_covered_breast(tmp_path):
    img = tmp_path / "suggestive.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("FEMALE_BREAST_COVERED")])
    assert clf.classify(str(img)) == ["suggestive"]


def test_unmapped_label_produces_no_tag(tmp_path):
    img = tmp_path / "face.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("FACE_FEMALE")])
    assert clf.classify(str(img)) == []


def test_severity_order_explicit_before_revealing_before_suggestive(tmp_path):
    img = tmp_path / "multi.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[
        _det("FEMALE_BREAST_COVERED"),    # → suggestive
        _det("BUTTOCKS_EXPOSED"),          # → revealing
        _det("FEMALE_BREAST_EXPOSED"),    # → explicit
    ])
    assert clf.classify(str(img)) == ["explicit", "revealing", "suggestive"]


def test_deduplicates_tags_from_multiple_labels(tmp_path):
    img = tmp_path / "dup.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[
        _det("FEMALE_BREAST_EXPOSED"),
        _det("FEMALE_GENITALIA_EXPOSED"),  # also → explicit
    ])
    assert clf.classify(str(img)) == ["explicit"]


def test_custom_label_map_remaps_to_single_tag(tmp_path):
    img = tmp_path / "custom.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(detections=[_det("FEMALE_BREAST_EXPOSED")])
    clf.label_map = {"FEMALE_BREAST_EXPOSED": "nsfw", "BUTTOCKS_EXPOSED": "nsfw"}
    result = clf.classify(str(img))
    assert result == ["nsfw"]


def test_returns_empty_on_detector_exception(tmp_path):
    img = tmp_path / "corrupt.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier()
    clf.detector.detect.side_effect = RuntimeError("onnxruntime error")
    assert clf.classify(str(img)) == []
