import logging


class DocProcessor:
    def __init__(self):
        self.docling_url = "http://docling:5001"
        self.tika_url = "http://tika:5001"

    def _get_num_pdf_pages(self, file_content: bytes) -> int:
        """
        Count the number of pages in a PDF uploaded via FastAPI.
        :param file_content:
        :return:
        """
        pass

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
        pass

    async def _docling_convert(self, file_content: bytes) -> list[dict]:
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
        markdown = "TBD"
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
        pass

    def _get_num_ppt_slides(self, file_content: bytes) -> int:
        """
        Count the number of pages in a PowerPoint uploaded via FastAPI.
        :param file_content:
        :return:
        """
        pass

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

    async def _tika_convert(self, file_content: bytes) -> list[dict]:
        """
        Fallback converter using Apache Tika to cover remaining file types.
        :param file_content: A file uploaded via FastAPI
        :return: A string containing the file content.
        """
        file_content = "TBD"
        return [{"type": "text", "text": file_content}]

    async def process(self, file_content: bytes, filename: str) -> list[dict]:
        try:
            filename = filename.lower()
            
            # Early return for small PDFs
            if filename.endswith(".pdf") and self._get_num_pdf_pages(file_content) < 16:
                return self._pdf_to_image_list(file_content, dpi=150)

            # Early return for small PPTXs
            if filename.endswith(".pptx") and self._get_num_ppt_slides(file_content) < 32:
                return self._ppt_to_image_list(file_content, dpi=120)

            # Unified fallback for word & large PDF/PPTX
            if filename.endswith((",docx", ".pdf", ".pptx")):
                return await self._docling_convert(file_content)

            # Default fallback for unsupported formats
            return await self._tika_convert(file_content)

        except Exception as e:
            # Log the error for debugging while gracefully falling back
            logging.warning(f"Document processing failed, falling back to Tika: {e}")
            return await self._tika_convert(file_content)
