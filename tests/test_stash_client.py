import pytest
from unittest.mock import patch, MagicMock
from src.stash_client import StashClient


SERVER = {"Scheme": "http", "Host": "localhost", "Port": 9999}


@pytest.fixture
def client():
    return StashClient(SERVER)


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": data}
    return resp


def test_count_images(client):
    with patch.object(client.session, "post", return_value=_mock_response({"findImages": {"count": 42}})):
        assert client.count_images() == 42


def test_find_or_create_tag_finds_existing(client):
    tag_data = {"findTags": {"tags": [{"id": "tag-123"}]}}
    with patch.object(client.session, "post", return_value=_mock_response(tag_data)):
        tag_id = client.find_or_create_tag("exclude")
    assert tag_id == "tag-123"


def test_find_or_create_tag_creates_when_missing(client):
    responses = [
        _mock_response({"findTags": {"tags": []}}),
        _mock_response({"tagCreate": {"id": "tag-new"}}),
    ]
    with patch.object(client.session, "post", side_effect=responses):
        tag_id = client.find_or_create_tag("exclude")
    assert tag_id == "tag-new"


def test_add_tag_to_image_skips_if_already_tagged(client):
    image_data = {"findImage": {"tags": [{"id": "tag-123"}]}}
    with patch.object(client.session, "post", return_value=_mock_response(image_data)) as mock_post:
        client.add_tag_to_image("img-1", "tag-123")
        # Only one call (to get existing tags), no mutation issued
        assert mock_post.call_count == 1


def test_add_tag_to_image_appends_new_tag(client):
    responses = [
        _mock_response({"findImage": {"tags": [{"id": "existing-tag"}]}}),
        _mock_response({"imageUpdate": {"id": "img-1"}}),
    ]
    with patch.object(client.session, "post", side_effect=responses) as mock_post:
        client.add_tag_to_image("img-1", "new-tag")
        assert mock_post.call_count == 2


def test_update_image_tags_removes_tag(client):
    with patch.object(client.session, "post", return_value=_mock_response({"imageUpdate": {"id": "img-1"}})) as mock_post:
        client.update_image_tags("img-1", [], ["stale-tag"], ["stale-tag", "keep-tag"])
        assert mock_post.call_count == 1
        sent = mock_post.call_args[1]["json"]["variables"]["input"]["tag_ids"]
        assert sent == ["keep-tag"]


def test_update_image_tags_noop_when_unchanged(client):
    with patch.object(client.session, "post") as mock_post:
        client.update_image_tags("img-1", ["existing"], [], ["existing"])
        mock_post.assert_not_called()
