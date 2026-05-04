from fastapi import FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool

from pipeline import DocProcessor
from cache import Cache

app = FastAPI()

file_processor = DocProcessor()
cache = Cache()


@app.post("/file2vlm-content")
async def upload_file(file: UploadFile = File(...)) -> list[dict]:
    """
    Convert an uploaded document to VLM content, using a SHA-256 cache to
    skip reprocessing for files that have already been seen.
    """
    filename = file.filename or ""
    file_content = await file.read()

    hash_key = await run_in_threadpool(cache.hash_file, file_content=file_content)

    cached = cache.read_cache(hash_key)
    if cached is not None:
        return cached

    vlm_content = await run_in_threadpool(
        file_processor.process, file_content=file_content, filename=filename
    )
    cache.write_cache(hash_key=hash_key, vlm_content=vlm_content)

    return vlm_content


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
