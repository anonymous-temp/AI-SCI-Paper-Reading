"""
Document Parser Service - Extract text from various manuscript formats
"""
import os
from typing import Optional, Tuple
from pathlib import Path
import re

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class DocumentParser:
    """
    Service for parsing manuscript files in various formats (.docx, .pdf, .txt)
    and extracting clean text content.
    """

    SUPPORTED_FORMATS = [".docx", ".pdf", ".txt"]
    MAX_FILE_SIZE_MB = 50

    def __init__(self):
        """Initialize document parser"""
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if required parsing libraries are available"""
        if not DOCX_AVAILABLE:
            print("Warning: python-docx not installed. .docx parsing will fail.")
        if not PDF_AVAILABLE:
            print("Warning: pypdf not installed. .pdf parsing will fail.")

    def parse(self, file_path: str) -> Tuple[str, dict]:
        """
        Parse a manuscript file and extract text content.

        Args:
            file_path: Path to the manuscript file

        Returns:
            Tuple of (text_content, metadata)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format not supported or file too large
            RuntimeError: If parsing fails
        """
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File size ({file_size_mb:.2f} MB) exceeds maximum allowed size ({self.MAX_FILE_SIZE_MB} MB)"
            )

        # Get file extension
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format: {file_ext}. Supported formats: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        # Parse based on file type
        try:
            if file_ext == ".docx":
                text, metadata = self._parse_docx(file_path)
            elif file_ext == ".pdf":
                text, metadata = self._parse_pdf(file_path)
            elif file_ext == ".txt":
                text, metadata = self._parse_txt(file_path)
            else:
                raise ValueError(f"Unsupported format: {file_ext}")

            # Clean and validate text
            text = self._clean_text(text)
            if not text or len(text.strip()) < 100:
                raise RuntimeError("Extracted text is empty or too short (< 100 characters)")

            metadata["file_path"] = file_path
            metadata["file_size_mb"] = file_size_mb
            metadata["format"] = file_ext

            return text, metadata

        except Exception as e:
            raise RuntimeError(f"Failed to parse document: {str(e)}")

    def _parse_docx(self, file_path: str) -> Tuple[str, dict]:
        """Parse .docx file"""
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx not installed. Run: pip install python-docx")

        doc = Document(file_path)

        # Extract paragraphs
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        text = "\n\n".join(paragraphs)

        # Extract tables
        table_count = len(doc.tables)

        # Extract basic metadata
        core_props = doc.core_properties
        metadata = {
            "title": core_props.title or "",
            "author": core_props.author or "",
            "created": str(core_props.created) if core_props.created else "",
            "modified": str(core_props.modified) if core_props.modified else "",
            "paragraph_count": len(paragraphs),
            "table_count": table_count,
        }

        return text, metadata

    def _parse_pdf(self, file_path: str) -> Tuple[str, dict]:
        """Parse .pdf file"""
        if not PDF_AVAILABLE:
            raise ImportError("pypdf not installed. Run: pip install pypdf")

        reader = PdfReader(file_path)

        # Extract text from all pages
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)

        text = "\n\n".join(pages_text)

        # Extract metadata
        pdf_info = reader.metadata
        metadata = {
            "title": pdf_info.get("/Title", "") if pdf_info else "",
            "author": pdf_info.get("/Author", "") if pdf_info else "",
            "created": str(pdf_info.get("/CreationDate", "")) if pdf_info else "",
            "page_count": len(reader.pages),
        }

        return text, metadata

    def _parse_txt(self, file_path: str) -> Tuple[str, dict]:
        """Parse .txt file"""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        metadata = {
            "line_count": text.count("\n"),
            "character_count": len(text),
        }

        return text, metadata

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text by:
        - Removing excessive whitespace
        - Normalizing line breaks
        - Removing hidden/invisible characters
        """
        # Remove zero-width characters (potential security issue)
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)

        # Normalize whitespace
        text = re.sub(r'\r\n', '\n', text)  # Windows line endings
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
        text = re.sub(r'\n{3,}', '\n\n', text)  # Multiple newlines to double newline

        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text.strip()

    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a file can be parsed without actually parsing it.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check existence
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        # Check format
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in self.SUPPORTED_FORMATS:
            return False, f"Unsupported format: {file_ext}"

        # Check size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            return False, f"File too large: {file_size_mb:.2f} MB (max: {self.MAX_FILE_SIZE_MB} MB)"

        # Check if file is readable
        try:
            with open(file_path, "rb") as f:
                f.read(1)
        except Exception as e:
            return False, f"File not readable: {str(e)}"

        return True, None
