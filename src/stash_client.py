import requests


class StashClient:
    """Thin GraphQL client for the local Stash server."""

    def __init__(self, server_connection: dict):
        scheme = server_connection.get("Scheme", "http")
        host = server_connection.get("Host", "localhost")
        port = server_connection.get("Port", 9999)
        self.url = f"{scheme}://{host}:{port}/graphql"
        cookie = server_connection.get("SessionCookie", {})
        self.session = requests.Session()
        if cookie:
            self.session.cookies.set(cookie.get("Name", "session"), cookie.get("Value", ""))

    def _query(self, query: str, variables: dict = None) -> dict:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self.session.post(self.url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    def count_images(self) -> int:
        query = """
        query CountImages {
            findImages(filter: { per_page: 1 }) {
                count
            }
        }
        """
        return self._query(query)["findImages"]["count"]

    def find_images(self, page: int = 1, per_page: int = 50) -> list[dict]:
        query = """
        query FindImages($filter: FindFilterType) {
            findImages(filter: $filter) {
                images {
                    id
                    visual_files {
                        ... on ImageFile {
                            path
                        }
                    }
                }
            }
        }
        """
        variables = {"filter": {"page": page, "per_page": per_page}}
        return self._query(query, variables)["findImages"]["images"]

    def find_or_create_tag(self, name: str) -> str:
        tag_id = self._find_tag(name)
        if tag_id:
            return tag_id
        return self._create_tag(name)

    def _find_tag(self, name: str) -> str | None:
        query = """
        query FindTag($name: String!) {
            findTags(tag_filter: { name: { value: $name, modifier: EQUALS } }) {
                tags { id }
            }
        }
        """
        tags = self._query(query, {"name": name})["findTags"]["tags"]
        return tags[0]["id"] if tags else None

    def _create_tag(self, name: str) -> str:
        query = """
        mutation TagCreate($input: TagCreateInput!) {
            tagCreate(input: $input) { id }
        }
        """
        return self._query(query, {"input": {"name": name}})["tagCreate"]["id"]

    def add_tag_to_image(self, image_id: str, tag_id: str):
        query = """
        mutation ImageUpdate($input: ImageUpdateInput!) {
            imageUpdate(input: $input) { id }
        }
        """
        # Read existing tags first to avoid clobbering them
        existing = self._get_image_tag_ids(image_id)
        if tag_id in existing:
            return
        self._query(query, {"input": {"id": image_id, "tag_ids": existing + [tag_id]}})

    def _get_image_tag_ids(self, image_id: str) -> list[str]:
        query = """
        query FindImage($id: ID!) {
            findImage(id: $id) {
                tags { id }
            }
        }
        """
        tags = self._query(query, {"id": image_id})["findImage"]["tags"]
        return [t["id"] for t in tags]
