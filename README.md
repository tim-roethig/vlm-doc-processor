# vlm-doc-processor

A small FastAPI service that converts uploaded documents (PDF, PPTX, DOCX, and
other office formats) into **VLM content** — a list of text/image segments
shaped to be dropped straight into a vision-language model prompt.

The output is a JSON array of segments, each one of:

```json
{"type": "text", "text": "..."}
{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
```

It bundles three services in `compose.yaml`:

- `doc-processor` — the FastAPI app in `api/` (exposed on port `8080`)
- `docling` — [docling-serve](https://github.com/docling-project/docling-serve)
  for converting office documents to Markdown with embedded images (port `5001`)
- `tika` — Apache Tika for fallback text extraction on anything else (port `9998`)

## Running it

Bring everything up with Docker Compose:

```bash
docker compose up --build
```

Once the stack is healthy, send a file to the API:

```bash
curl -X POST http://localhost:8080/file2vlm-content \
  -F "file=@api/test_data/short.pdf"
```

The response is a JSON list of `text` / `image_url` segments.

### Configuration

Behaviour is tuned through environment variables on the `doc-processor`
service (defaults shown):

| Variable | Default | Description |
| --- | --- | --- |
| `DOCLING_URL` | `http://docling:5001` | Docling-serve endpoint |
| `TIKA_URL` | `http://tika:9998` | Tika endpoint |
| `PDF_DPI` | `150` | DPI for direct PDF page rendering |
| `PP_DPI` | `120` | DPI for PPTX slide rendering |
| `MAX_DIRECT_INPUT_PDF_PAGES` | `16` | PDFs at or below this go straight to images |
| `MAX_DIRECT_INPUT_PP_SLIDES` | `32` | PPTXs at or below this go straight to images |
| `CACHE_DIR` | `/var/cache/docs` | Where cached results are written |

## How the pipeline works

`DocProcessor.process` (`api/pipeline.py`) dispatches on file extension and
size, preferring the path that preserves the most visual information and
falling back to text extraction when nothing better is available.

1. **Small PDFs** (`.pdf`, ≤ `MAX_DIRECT_INPUT_PDF_PAGES`) — each page is
   rendered to a PNG with PyMuPDF at `PDF_DPI` and emitted as a single
   `image_url` segment. The VLM sees the page exactly as a human would.
2. **Small PPTXs** (`.pptx`, ≤ `MAX_DIRECT_INPUT_PP_SLIDES`) — converted to
   PDF via headless LibreOffice (`soffice`) using a temp user profile, then
   rendered the same way as small PDFs at `PP_DPI`.
3. **Larger PDFs / PPTXs and all DOCX files** — sent to docling-serve, which
   returns Markdown with embedded base64 images. The Markdown is then split on
   image tags into an interleaved sequence of `text` and `image_url` segments.
4. **Anything else** — handed to Apache Tika, which returns plain text wrapped
   in a single `text` segment.
5. **Failure fallback** — any exception in steps 1–3 is logged and falls
   through to Tika so the request still returns something usable.

The `text`/`image_url` shape is identical across paths, so callers don't have
to care which branch produced the result.

## How the caching works

Caching lives in `api/cache.py` and is wired into the request handler in
`api/main.py`.

- **Key**: SHA-256 hex digest of the raw uploaded bytes. Identical files
  always produce the same key, regardless of filename.
- **Storage**: one JSON file per document at `<CACHE_DIR>/<sha256>.json`
  containing the VLM-content list returned by the pipeline.
- **Writes are atomic**: results are written to `<sha256>.json.tmp` first and
  then `os.replace`d into place, so a concurrent reader never sees a partially
  written file.
- **Lookup flow** in `/file2vlm-content`:
  1. Hash the uploaded bytes.
  2. If `<sha256>.json` exists, load and return it — the pipeline isn't run.
  3. Otherwise process the file, persist the result, then return it.

The hashing and pipeline calls are dispatched via
`fastapi.concurrency.run_in_threadpool` so the event loop stays responsive
during CPU-bound rendering or blocking HTTP calls to docling/tika.

To clear the cache, delete the contents of `CACHE_DIR` (e.g. by removing the
volume or `rm`-ing the JSON files); there is no eviction policy or TTL.
