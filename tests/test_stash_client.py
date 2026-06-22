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


def test_count_images_by_tag(client):
    data = {"findImages": {"count": 7}}
    with patch.object(client.session, "post", return_value=_mock_response(data)) as mock_post:
        assert client.count_images_by_tag("tag-123") == 7
        sent = mock_post.call_args[1]["json"]
        variables = sent["variables"]
        assert variables["image_filter"]["tags"]["value"] == ["tag-123"]
        assert variables["image_filter"]["tags"]["modifier"] == "INCLUDES_ALL"


def test_find_images_by_tag_returns_image_list(client):
    data = {
        "findImages": {
            "images": [
                {
                    "id": "img-1",
                    "visual_files": [{"path": "/data/img.jpg"}],
                    "tags": [{"id": "tag-123"}],
                }
            ]
        }
    }
    with patch.object(client.session, "post", return_value=_mock_response(data)) as mock_post:
        results = client.find_images_by_tag("tag-123", page=2, per_page=10)
        assert results == [{"id": "img-1", "path": "/data/img.jpg", "tag_ids": ["tag-123"]}]
        variables = mock_post.call_args[1]["json"]["variables"]
        assert variables["image_filter"]["tags"]["value"] == ["tag-123"]
        assert variables["filter"]["page"] == 2
        assert variables["filter"]["per_page"] == 10


def test_find_images_by_tag_handles_missing_visual_files(client):
    data = {
        "findImages": {
            "images": [{"id": "img-2", "visual_files": [], "tags": []}]
        }
    }
    with patch.object(client.session, "post", return_value=_mock_response(data)):
        results = client.find_images_by_tag("tag-123")
        assert results == [{"id": "img-2", "path": None, "tag_ids": []}]
