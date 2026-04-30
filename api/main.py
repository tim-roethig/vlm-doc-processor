from fastapi import FastAPI, File, UploadFile

from pipeline import DocProcessor
from cache import Cache


app = FastAPI()

file_processor = DocProcessor()
cache = Cache()

@app.post("/file2vlm-content")
async def upload_file(file: UploadFile = File(...)) -> list[dict]:
    filename = file.filename
    file_content = await file.read()
    
    hash_key = cache.hash_file(file_content=file_content)

    vlm_content = cache.read_cache(hash_key)
    if vlm_content:
        return vlm_content

    vlm_content = await file_processor.process(file_content=file_content, filename=filename)
    cache.write_cache(hash_key=hash_key, vlm_content=vlm_content)

    return vlm_content


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8081)
