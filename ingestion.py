import os
import re
import shutil
import unicodedata
from pathlib import Path

import pypdf
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

class IngestionEngine:
    def __init__(self, source_path, ui_callback=None, user_chunk_size=5000):
        # We store the path but do NOT perform file operations yet
        self.source_path = Path(source_path) if source_path else None
        self.ui_callback = ui_callback

        # FIXED PATHS
        self.base_dir = Path("LexiFlow")
        self.input_dir = self.base_dir / "1_input_copy"
        self.extract_dir = self.base_dir / "2_extracted_chunks"

        # Configuration
        self.target = int(user_chunk_size)
        self.cap = int(user_chunk_size * 1.25)  # Grace zone

    def emit(self, log_msg, progress=5):
        if self.ui_callback:
            self.ui_callback({"status": "Ingesting", "progress": progress, "log": log_msg})
        else:
            print(log_msg)

    def sanitize_text(self, raw: str) -> str:
        """Cleans and standardizes text for AI processing."""
        safe = raw.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        safe = unicodedata.normalize("NFC", safe)
        safe = re.sub(r'[\U00010000-\U0010FFFF]', '', safe)
        safe = re.sub(r'\n\s*\n', '\n\n', safe)
        safe = re.sub(r'[ \t]+', ' ', safe)
        return safe.strip()

    def extract_text(self):
        """Extracts text based on file extension."""
        if not self.source_path or not self.source_path.exists():
            self.emit("❌ Error: Source file not found.")
            return ""

        ext = self.source_path.suffix.lower()
        text = ""
        self.emit(f"📂 Opening {ext.upper()} file...", 7)

        try:
            if ext == ".pdf":
                with open(self.source_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    pages = []
                    for i, page in enumerate(reader.pages):
                        if i % 10 == 0:
                            self.emit(f"Reading PDF Page {i}...", 8)
                        try:
                            page_text = page.extract_text()
                            if page_text:
                                pages.append(self.sanitize_text(page_text))
                        except Exception:
                            continue
                    text = " ".join(pages)

            elif ext == ".docx":
                doc = Document(str(self.source_path))
                text = "\n".join([para.text for para in doc.paragraphs])
                text = self.sanitize_text(text)

            elif ext == ".epub":
                book = epub.read_epub(str(self.source_path))
                pages = []
                for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                    try:
                        soup = BeautifulSoup(item.get_content(), 'html.parser')
                        pages.append(self.sanitize_text(soup.get_text()))
                    except Exception:
                        continue
                text = "\n".join(pages)

            else:  # TXT fallback
                text = self.source_path.read_text(encoding="utf-8", errors="ignore")
                text = self.sanitize_text(text)

        except Exception as e:
            self.emit(f"❌ Critical Extraction Error: {str(e)}")
            return ""

        return text

    def smart_split(self, text):
        """Splits text into chunks at natural paragraph or sentence breaks."""
        chunks = []
        self.emit("✂️ Segmenting text into AI-ready chunks...", 12)

        while len(text) > 0:
            if len(text) <= self.cap:
                chunks.append(text.strip())
                break

            breakpoint = text.rfind('\n\n', self.target, self.cap)
            if breakpoint == -1:
                breakpoint = text.rfind('. ', self.target, self.cap)
            if breakpoint == -1:
                breakpoint = text.rfind(' ', self.target, self.cap)

            if breakpoint == -1:
                breakpoint = self.target
            else:
                breakpoint += 1

            chunks.append(text[:breakpoint].strip())
            text = text[breakpoint:].lstrip()

        return chunks

    def run(self):
        """Orchestrates the ingestion process."""
        # 1. Create folders only when run starts
        for folder in [self.input_dir, self.extract_dir]:
            folder.mkdir(parents=True, exist_ok=True)

        # 2. Perform file copy safely
        if self.source_path and self.source_path.exists():
            shutil.copy(self.source_path, self.input_dir / self.source_path.name)
        else:
            self.emit("❌ Ingestion failed: File not found.")
            return False

        # 3. Extract and Split
        raw_text = self.extract_text()
        if not raw_text or len(raw_text) < 10:
            self.emit("❌ Error: No text could be extracted.")
            return False

        chunks = self.smart_split(raw_text)

        # 4. Save Chunks
        for i, chunk in enumerate(chunks):
            chunk_file = self.extract_dir / f"chunk_{i+1:04d}.txt"
            chunk_file.write_text(chunk, encoding="utf-8")

        self.emit(f"✅ Created {len(chunks)} chunks successfully!", 15)
        return True

def process(source_path, ui_callback=None, user_chunk_size=15000):
    ingestor = IngestionEngine(source_path, ui_callback, user_chunk_size=user_chunk_size)
    return ingestor.run()