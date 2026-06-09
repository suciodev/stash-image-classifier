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

    def find_image_by_id(self, image_id: str) -> dict | None:
        query = """
        query FindImage($id: ID!) {
            findImage(id: $id) {
                id
                visual_files {
                    ... on ImageFile {
                        path
                    }
                }
                tags { id }
            }
        }
        """
        result = self._query(query, {"id": str(image_id)})["findImage"]
        if not result:
            return None
        path = result["visual_files"][0]["path"] if result.get("visual_files") else None
        return {"id": result["id"], "path": path, "tag_ids": [t["id"] for t in result.get("tags", [])]}

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
                    tags { id }
                }
            }
        }
        """
        variables = {"filter": {"page": page, "per_page": per_page}}
        raw = self._query(query, variables)["findImages"]["images"]
        return [
            {
                "id": img["id"],
                "path": img["visual_files"][0]["path"] if img.get("visual_files") else None,
                "tag_ids": [t["id"] for t in img.get("tags", [])],
            }
            for img in raw
        ]

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

    def update_image_tags(
        self,
        image_id: str,
        add_tag_ids: list[str],
        remove_tag_ids: list[str],
        existing_tag_ids: list[str],
    ):
        """Atomically add and remove tags in a single imageUpdate call."""
        remove_set = set(remove_tag_ids)
        final_ids = [tid for tid in existing_tag_ids if tid not in remove_set]
        for tid in add_tag_ids:
            if tid not in final_ids:
                final_ids.append(tid)
        if set(final_ids) == set(existing_tag_ids):
            return
        query = """
        mutation ImageUpdate($input: ImageUpdateInput!) {
            imageUpdate(input: $input) { id }
        }
        """
        self._query(query, {"input": {"id": image_id, "tag_ids": final_ids}})

    def add_tag_to_image(self, image_id: str, tag_id: str, existing_tag_ids: list[str] | None = None):
        if existing_tag_ids is None:
            existing_tag_ids = self._get_image_tag_ids(image_id)
        self.update_image_tags(image_id, [tag_id], [], existing_tag_ids)

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
