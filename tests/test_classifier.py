import pytest
from unittest.mock import patch, MagicMock
from src.classifier import ImageClassifier


def _make_classifier(boxes=None):
    """Return a classifier with the YOLO model mocked out."""
    mock_model = MagicMock()
    result = MagicMock()
    result.boxes = boxes if boxes is not None else []
    mock_model.return_value = [result]

    with patch("src.classifier.YOLO", return_value=mock_model):
        clf = ImageClassifier()
    clf.model = mock_model
    return clf


def test_has_person_returns_false_for_missing_file():
    clf = _make_classifier()
    assert clf.has_person("/nonexistent/path/image.jpg") is False


def test_has_person_returns_false_when_no_boxes(tmp_path):
    img = tmp_path / "blank.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[])
    assert clf.has_person(str(img)) is False


def test_has_person_returns_true_when_boxes_present(tmp_path):
    img = tmp_path / "person.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[MagicMock()])
    assert clf.has_person(str(img)) is True


def test_model_called_with_person_class_only(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake")
    clf = _make_classifier(boxes=[])
    clf.has_person(str(img))
    call_kwargs = clf.model.call_args[1]
    assert call_kwargs["classes"] == [0]
    assert call_kwargs["verbose"] is False
