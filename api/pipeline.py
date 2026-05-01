import base64
import io
import logging
import os
import re
import subprocess
import tempfile

import fitz
import httpx
from pptx import Presentation


class DocProcessor:
    def __init__(self):
        self.docling_url = os.environ.get("DOCLING_URL", "http://docling:5001")
        self.tika_url = os.environ.get("TIKA_URL", "http://tika:9998")
        self.pdf_dpi = int(os.environ.get("PDF_DPI", 150))
        self.pp_dpi = int(os.environ.get("PP_DPI", 120))
        self.max_direct_input_pdf_pages = int(os.environ.get("MAX_DIRECT_INPUT_PDF_PAGES", 16))
        self.max_direct_input_pp_slides = int(os.environ.get("MAX_DIRECT_INPUT_PP_SLIDES", 32))

    def _get_num_pdf_pages(self, file_content: bytes) -> int:
        """
        Count the number of pages in a PDF uploaded via FastAPI.
        :param file_content:
        :return:
        """
        with fitz.open(stream=file_content, filetype="pdf") as doc:
            return doc.page_count

    def _pdf_to_image_list(self, file_content: bytes, dpi: int) -> list[dict]:
        """
        :param file_content: A PDF uploaded via FastAPI
        :param dpi: The dpi of each image.
        :return: A list of dictionaries in the form of a VLM content input
        [
            {"type": "image_url", "image_url": {"url": "<1st PAGE AS BASE64 IMAGE>"}},
            {"type": "image_url", "image_url": {"url": "<2nd PAGE AS BASE64 IMAGE>"}},
            {"type": "image_url", "image_url": {"url": "<3rd PAGE AS BASE64 IMAGE>"}},
            ...
        ]
        """
        out: list[dict] = []
        with fitz.open(stream=file_content, filetype="pdf") as doc:
            for page in doc:
                png_bytes = page.get_pixmap(dpi=dpi).tobytes("png")
                b64 = base64.b64encode(png_bytes).decode("ascii")
                out.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
        return out

    def _docling_convert(self, file_content: bytes) -> list[dict]:
        """
        Convert a file to Markdown using the docling serve API with images embedded as base64.

        :param file_content: A file uploaded via FastAPI
        :return: A list of dictionaries in the form of a VLM content input
        [
            {"type": "text", "text": "Text until the first image"},
            {"type": "image_url", "image_url": {"url": "<IMAGE AS BASE64>"}},
            {"type": "text", "text": "More text after the first image."},
            ...
        ]
        """
        files = [("files", ("doc.bin", file_content, "application/octet-stream"))]
        data = [("to_formats", "md"), ("image_export_mode", "embedded")]
        r = httpx.post(
            f"{self.docling_url}/v1/convert/file",
            files=files,
            data=data,
            timeout=300,
        )
        r.raise_for_status()
        markdown = r.json()["document"]["md_content"]
        return self._markdown_to_vlm_content(markdown)

    def _markdown_to_vlm_content(self, md: str) -> list[dict]:
        """
        Transform a Markdown string with embedded base64 images into a VLM content input.

        :param md: A Markdown string potentially containing base64 encoded images
            ## Oracle Corporation
            Recommendation
            ![Image](data:image/png;base64,iVBORw0KGgoAAAANSUh...U5ErkJggg==)

            ## Equity Analyst Angelo Zino, CFA
            GICS Sector
            Information Technology
            Sub-Industry
            Systems Software
            ![Image](data:image/png;base64,iVBORw0KGgoAA...AAAAElFTkSuQmCC)

            ## Price
            USD 149.27 (as of market close Mar 14, 2025)
            12-Mo. Target Price
            USD 185.00
        :return: A list of dictionaries in the form of a VLM content input
        [
            {"type": "text", "text": "Text until the first image"},
            {"type": "image_url", "image_url": {"url": "<IMAGE AS BASE64>"}},
            {"type": "text", "text": "More text after the first image."},
            ...
        ]
        """
        pattern = re.compile(r"!\[[^\]]*\]\((data:image/[^;]+;base64,[^)]+)\)")
        parts = pattern.split(md)
        out: list[dict] = []
        for i, segment in enumerate(parts):
            if i % 2 == 0:
                text = segment.strip()
                if text:
                    out.append({"type": "text", "text": text})
            else:
                out.append({"type": "image_url", "image_url": {"url": segment}})
        return out

    def _get_num_ppt_slides(self, file_content: bytes) -> int:
        """
        Count the number of pages in a PowerPoint uploaded via FastAPI.
        :param file_content:
        :return:
        """
        return len(Presentation(io.BytesIO(file_content)).slides)

    def _ppt_to_image_list(self, file_content: bytes, dpi: int) -> list[dict]:
        """
        :param file_content: a pptx uploaded via FastAPI
        :param dpi: The dpi of each image.
        :return: A list of dictionaries in the form of a VLM content input
        [
            {"type": "image_url", "image_url": {"url": "<1st SLIDE AS BASE64 IMAGE>"}},
            {"type": "image_url", "image_url": {"url": "<2nd SLIDE AS BASE64 IMAGE>"}},
            {"type": "image_url", "image_url": {"url": "<3rd SLIDE AS BASE64 IMAGE>"}},
            ...
        ]
        """
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "input.pptx")
            with open(in_path, "wb") as f:
                f.write(file_content)
            profile_uri = f"file://{tmp}/lo-profile"
            subprocess.run(
                [
                    "soffice",
                    f"-env:UserInstallation={profile_uri}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp,
                    in_path,
                ],
                check=True,
                timeout=120,
                capture_output=True,
            )
            with open(os.path.join(tmp, "input.pdf"), "rb") as f:
                pdf_bytes = f.read()
        return self._pdf_to_image_list(pdf_bytes, dpi=dpi)

    def _tika_convert(self, file_content: bytes) -> list[dict]:
        """
        Fallback converter using Apache Tika to cover remaining file types.
        :param file_content: A file uploaded via FastAPI
        :return: A string containing the file content.
        """
        r = httpx.put(
            f"{self.tika_url}/tika",
            content=file_content,
            headers={"Accept": "text/plain"},
            timeout=120,
        )
        r.raise_for_status()
        return [{"type": "text", "text": r.text}]

    def process(self, file_content: bytes, filename: str) -> list[dict]:
        try:
            filename = filename.lower()

            # Early return for small PDFs
            if (
                filename.endswith(".pdf")
                and self._get_num_pdf_pages(file_content) <= self.max_direct_input_pdf_pages
            ):
                return self._pdf_to_image_list(file_content, dpi=self.pdf_dpi)

            # Early return for small PPTXs
            if (
                filename.endswith(".pptx")
                and self._get_num_ppt_slides(file_content) <= self.max_direct_input_pp_slides
            ):
                return self._ppt_to_image_list(file_content, dpi=self.pp_dpi)

            # Unified fallback for word & large PDF/PPTX
            if filename.endswith((".docx", ".pdf", ".pptx")):
                return self._docling_convert(file_content)

            # Default fallback for unsupported formats
            return self._tika_convert(file_content)

        except Exception as e:
            # Log the error for debugging while gracefully falling back
            logging.warning(f"Document processing failed, falling back to Tika: {e}")
            return self._tika_convert(file_content)
