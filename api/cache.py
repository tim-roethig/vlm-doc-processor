class Cache:
    def __init__(self):
        self.cache_dir = "/var/cache/docs"

    def hash_file(self, file_content: bytes) -> str:
        """
        Hash a file using sha256.
        :param file_content:
        :return:
        """
        pass

    def write_cache(self, hash_key: str, vlm_content: list[dict]):
        """
        Store vlm_content as JSON in self.cache_dir under <hash_key>.json.
        :param hash_key:
        :param vlm_content:
        :return:
        """
        pass

    def read_cache(self, hash_key: str) -> None | list[dict]:
        """
        Check if a file exists in cache_dir under the name <hash_key>.json exist.
        If yes read it into a list and return it. If not, return None.
        :param hash_key:
        :return:
        """
        pass
