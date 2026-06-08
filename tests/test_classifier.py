import pytest
from unittest.mock import patch, MagicMock
from src.classifier import ImageClassifier


def _make_box(x1, y1, x2, y2, conf=0.90):
    box = MagicMock()
    box.xyxy = [MagicMock()]
    box.xyxy[0].tolist.return_value = [x1, y1, x2, y2]
    box.conf = [conf]
    return box


def _make_classifier(boxes=None, orig_shape=(1000, 1000)):
    mock_model = MagicMock()
    result = MagicMock()
    result.boxes = boxes if boxes is not None else []
    result.orig_shape = orig_shape
    mock_model.return_value = [result]

    with patch("src.classifier.YOLO", return_value=mock_model):
        clf = ImageClassifier()
    clf.model = mock_model
    return clf


def test_returns_false_for_missing_file():
    clf = _make_classifier()
    assert clf.has_person("/nonexistent/image.jpg") is False


def test_returns_false_when_no_detections(tmp_path):
    img = tmp_path / "blank.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[])
    assert clf.has_person(str(img)) is False


def test_returns_true_for_large_confident_box(tmp_path):
    # 400x400 box in a 1000x1000 image = 16% area, conf 0.90
    img = tmp_path / "person.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[_make_box(300, 300, 700, 700, conf=0.90)])
    assert clf.has_person(str(img)) is True


def test_returns_false_for_small_box_below_area_threshold(tmp_path):
    # 20x20 box in 1000x1000 image = 0.04% area — below 5% default
    img = tmp_path / "tiny.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[_make_box(0, 0, 20, 20, conf=0.90)])
    assert clf.has_person(str(img)) is False



def test_model_called_with_min_confidence_and_person_class(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[])
    clf.has_person(str(img))
    call_kwargs = clf.model.call_args[1]
    assert call_kwargs["classes"] == [0]
    assert call_kwargs["conf"] == clf.min_confidence
    assert call_kwargs["verbose"] is False
