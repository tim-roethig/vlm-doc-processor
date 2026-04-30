import asyncio
import base64
import io
import logging
import os
import re
import subprocess
import tempfile
from typing import Awaitable, Callable

import httpx
import pypdfium2 as pdfium
from pypdf import PdfReader
from pptx import Presentation

logger = logging.getLogger(__name__)


_IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\((data:image/[^;]+;base64,[^)]+)\)")


class DocProcessor:
    def __init__(self):
        self.docling_url = os.environ.get("DOCLING_URL", "http://docling:5001")
        self.tika_url = os.environ.get("TIKA_URL", "http://tika:9998")
        self.docling_timeout = float(os.environ.get("DOCLING_TIMEOUT", "300"))
        self.tika_timeout = float(os.environ.get("TIKA_TIMEOUT", "120"))
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_num_pdf_pages(self, file_content: bytes) -> int:
        return len(PdfReader(io.BytesIO(file_content)).pages)

    def _pdf_to_image_list(self, file_content: bytes, dpi: int) -> list[dict]:
        scale = dpi / 72
        pdf = pdfium.PdfDocument(file_content)
        try:
            result: list[dict] = []
            for page in pdf:
                pil_image = page.render(scale=scale).to_pil()
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                result.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
            return result
        finally:
            pdf.close()

    async def _docling_convert(self, file_content: bytes, filename: str) -> list[dict]:
        client = await self._get_client()
        files = {"files": (filename, file_content)}
        data = {
            "to_formats": "md",
            "image_export_mode": "embedded",
        }
        response = await client.post(
            f"{self.docling_url}/v1/convert/file",
            files=files,
            data=data,
            timeout=self.docling_timeout,
        )
        response.raise_for_status()
        payload = response.json()

        markdown = payload.get("document", {}).get("md_content") or payload.get("md_content") or ""
        if not markdown:
            raise ValueError("Docling returned an empty markdown document")

        return self._markdown_to_vlm_content(markdown)

    def _markdown_to_vlm_content(self, md: str) -> list[dict]:
        result: list[dict] = []
        cursor = 0
        for match in _IMAGE_MD_RE.finditer(md):
            text_segment = md[cursor : match.start()].strip()
            if text_segment:
                result.append({"type": "text", "text": text_segment})
            data_url = match.group(1)
            result.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                }
            )
            cursor = match.end()

        tail = md[cursor:].strip()
        if tail:
            result.append({"type": "text", "text": tail})

        return result

    def _get_num_ppt_slides(self, file_content: bytes) -> int:
        return len(Presentation(io.BytesIO(file_content)).slides)

    def _pptx_bytes_to_pdf_bytes(self, file_content: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "input.pptx")
            with open(src_path, "wb") as f:
                f.write(file_content)

            proc = subprocess.run(
                [
                    "soffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmpdir,
                    src_path,
                ],
                capture_output=True,
                timeout=300,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"LibreOffice conversion failed: {proc.stderr.decode(errors='replace')}"
                )

            pdf_path = os.path.join(tmpdir, "input.pdf")
            if not os.path.exists(pdf_path):
                raise RuntimeError("LibreOffice did not produce a PDF output")

            with open(pdf_path, "rb") as f:
                return f.read()

    def _ppt_to_image_list(self, file_content: bytes, dpi: int) -> list[dict]:
        pdf_bytes = self._pptx_bytes_to_pdf_bytes(file_content)
        return self._pdf_to_image_list(pdf_bytes, dpi)

    async def _tika_convert(self, file_content: bytes) -> list[dict]:
        client = await self._get_client()
        response = await client.put(
            f"{self.tika_url}/tika",
            content=file_content,
            headers={"Accept": "text/plain"},
            timeout=self.tika_timeout,
        )
        response.raise_for_status()
        return [{"type": "text", "text": response.text}]

    async def _try(
        self,
        label: str,
        func: Callable[[], Awaitable[list[dict]] | list[dict]],
    ) -> list[dict] | None:
        try:
            result = func()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            logger.warning("%s failed: %s", label, e)
            return None

    async def process(self, file_content: bytes, filename: str) -> list[dict]:
        filename = filename.lower()

        ladder: list[tuple[str, Callable[[], Awaitable[list[dict]] | list[dict]]]] = []

        if filename.endswith(".pdf"):
            try:
                num_pages = self._get_num_pdf_pages(file_content)
            except Exception as e:
                logger.warning("Failed to count PDF pages: %s", e)
                num_pages = None

            if num_pages is not None and num_pages < 16:
                ladder.append(
                    (
                        "pdf-image-render",
                        lambda: asyncio.to_thread(self._pdf_to_image_list, file_content, 150),
                    )
                )
            ladder.append(("docling", lambda: self._docling_convert(file_content, filename)))

        elif filename.endswith(".pptx"):
            try:
                num_slides = self._get_num_ppt_slides(file_content)
            except Exception as e:
                logger.warning("Failed to count PPTX slides: %s", e)
                num_slides = None

            if num_slides is not None and num_slides < 32:
                ladder.append(
                    (
                        "pptx-image-render",
                        lambda: asyncio.to_thread(self._ppt_to_image_list, file_content, 120),
                    )
                )
            ladder.append(("docling", lambda: self._docling_convert(file_content, filename)))

        elif filename.endswith(".docx"):
            ladder.append(("docling", lambda: self._docling_convert(file_content, filename)))

        ladder.append(("tika", lambda: self._tika_convert(file_content)))

        for label, step in ladder:
            result = await self._try(label, step)
            if result:
                return result

        raise RuntimeError(f"All converters failed for {filename}")
