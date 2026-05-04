import hashlib
import json
import os


class Cache:
    def __init__(self):
        self.cache_dir = os.environ.get("CACHE_DIR", "/var/cache/docs")
        os.makedirs(self.cache_dir, exist_ok=True)

    def hash_file(self, file_content: bytes) -> str:
        """
        Hash a file using sha256.
        :param file_content:
        :return:
        """
        return hashlib.sha256(file_content).hexdigest()

    def write_cache(self, hash_key: str, vlm_content: list[dict]):
        """
        Store vlm_content as JSON in self.cache_dir under <hash_key>.json.
        :param hash_key:
        :param vlm_content:
        :return:
        """
        path = os.path.join(self.cache_dir, f"{hash_key}.json")
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(vlm_content, f)
        os.replace(tmp_path, path)

    def read_cache(self, hash_key: str) -> None | list[dict]:
        """
        Check if a file exists in cache_dir under the name <hash_key>.json exist.
        If yes read it into a list and return it. If not, return None.
        :param hash_key:
        :return:
        """
        path = os.path.join(self.cache_dir, f"{hash_key}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
