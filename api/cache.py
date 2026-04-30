import hashlib
import json
import os


class Cache:
    def __init__(self):
        self.cache_dir = "/var/cache/docs"
        os.makedirs(self.cache_dir, exist_ok=True)

    def hash_file(self, file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()

    def write_cache(self, hash_key: str, vlm_content: list[dict]):
        path = os.path.join(self.cache_dir, f"{hash_key}.json")
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(vlm_content, f)
        os.replace(tmp_path, path)

    def read_cache(self, hash_key: str) -> None | list[dict]:
        path = os.path.join(self.cache_dir, f"{hash_key}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None
