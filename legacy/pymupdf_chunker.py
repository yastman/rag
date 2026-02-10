#!/usr/bin/env python3
"""
PyMuPDF Fallback Chunker for Large Legal PDFs
Fast, no ML, regex-based structure detection
"""

import re
import unicodedata

import fitz  # PyMuPDF


class PyMuPDFChunker:
    """
    Fallback chunker for when Docling times out.

    Features:
    - Fast text extraction (no ML)
    - Legal document structure detection (Ukrainian)
    - Smart chunking by articles or token size
    - Text normalization (NFC, soft hyphens, line joining)
    - Metadata extraction
    """

    # Ukrainian legal document patterns
    PATTERNS = {
        "book": re.compile(
            r"^Книга\s+(перша|друга|третя|четверта|п.ята|шоста|сьома|восьма|дев.ята|десята|\d+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "section": re.compile(
            r"^Розділ\s+([IVXLCDM]+|перший|другий|третій|\d+)", re.IGNORECASE | re.MULTILINE
        ),
        "chapter": re.compile(r"^Глава\s+(\d+|перша|друга|третя)", re.IGNORECASE | re.MULTILINE),
        "article": re.compile(r"^Стаття\s+(\d+)\.?\s*(.*?)$", re.IGNORECASE | re.MULTILINE),
        "final_provisions": re.compile(r"^Прикінцеві положення", re.IGNORECASE | re.MULTILINE),
        # Russian patterns (for Criminal Code RU)
        "book_ru": re.compile(
            r"^Книга\s+(первая|вторая|третья|четвертая|пятая|\d+)", re.IGNORECASE | re.MULTILINE
        ),
        "section_ru": re.compile(
            r"^Раздел\s+([IVXLCDM]+|первый|второй|третий|\d+)", re.IGNORECASE | re.MULTILINE
        ),
        "chapter_ru": re.compile(r"^Глава\s+(\d+)", re.IGNORECASE | re.MULTILINE),
        "article_ru": re.compile(r"^Статья\s+(\d+)\.?\s*(.*?)$", re.IGNORECASE | re.MULTILINE),
    }

    def __init__(
        self,
        target_chunk_size: int = 600,
        min_chunk_size: int = 400,
        max_chunk_size: int = 800,
        overlap_percent: float = 0.12,  # 12% overlap
    ):
        """
        Initialize chunker.

        Args:
            target_chunk_size: Target tokens per chunk
            min_chunk_size: Minimum tokens per chunk
            max_chunk_size: Maximum tokens per chunk
            overlap_percent: Overlap between chunks (0.0-0.5)
        """
        self.target_chunk_size = target_chunk_size
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_percent = overlap_percent

    def chunk_pdf(self, pdf_path: str) -> list[dict]:
        """
        Chunk PDF file into structured chunks.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of chunks with text and metadata
        """
        # Extract text from PDF
        doc = fitz.open(pdf_path)
        pages_text = []

        for page_num, page in enumerate(doc):
            text = page.get_text("text")
            pages_text.append({"page_num": page_num + 1, "text": text})

        doc.close()

        # Combine all text
        full_text = "\n\n".join([p["text"] for p in pages_text])

        # Normalize text
        normalized_text = self.normalize_text(full_text)

        # Detect structure and chunk
        return self.chunk_by_structure(normalized_text, pages_text)

    def normalize_text(self, text: str) -> str:
        """
        Normalize text for better processing.

        Steps:
        1. Unicode NFC normalization
        2. Remove soft hyphens (\u00ad)
        3. Join broken lines (no punctuation at end)
        4. Clean multiple spaces/newlines
        5. Remove page numbers/headers
        """
        # 1. NFC normalization
        text = unicodedata.normalize("NFC", text)

        # 2. Remove soft hyphens
        text = text.replace("\u00ad", "")
        text = text.replace("\xad", "")  # Another variant

        # 3. Join broken lines (word continues on next line)
        # Pattern: "word-\nword" → "wordword"
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # 4. Join lines without punctuation
        # Pattern: "word\nword" → "word word"
        # BUT: DO NOT join if next line starts with legal structure markers
        # Use negative lookahead to prevent joining before Статья, Глава, etc.
        text = re.sub(
            r"([^\.\?\!:;,])\s*\n\s*(?!(Статья|Стаття|Глава|Розділ|Раздел|Книга)\s)([а-яА-ЯіІїЇєЄґҐa-zA-Z])",
            r"\1 \3",
            text,
            flags=re.IGNORECASE,
        )

        # 5. Clean multiple spaces
        text = re.sub(r" +", " ", text)

        # 6. Clean multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 7. Remove common page footers/headers patterns
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)  # Standalone page numbers
        text = re.sub(r"\n\s*Стор\.\s*\d+\s*\n", "\n", text)  # "Стор. 123"

        return text.strip()

    def chunk_by_structure(self, text: str, pages_info: list[dict]) -> list[dict]:
        """
        Chunk text by legal document structure.

        Strategy:
        1. Try to split by articles (Стаття)
        2. If article too long → split by token size with overlap
        3. If no articles found → split by paragraphs/tokens
        """
        chunks = []

        # Find all articles
        articles = list(self.PATTERNS["article"].finditer(text))
        if not articles:
            # Fallback: try Russian patterns
            articles = list(self.PATTERNS["article_ru"].finditer(text))

        if articles:
            # Chunk by articles
            chunks = self._chunk_by_articles(text, articles, pages_info)
        else:
            # Fallback: chunk by size
            chunks = self._chunk_by_size(text, pages_info)

        return chunks

    def _chunk_by_articles(
        self, text: str, articles: list[re.Match], pages_info: list[dict]
    ) -> list[dict]:
        """Chunk by article boundaries."""
        chunks = []

        for i, article_match in enumerate(articles):
            article_num = article_match.group(1)
            article_title = article_match.group(2).strip() if article_match.lastindex >= 2 else ""

            # Extract article text
            start_pos = article_match.start()
            end_pos = articles[i + 1].start() if i + 1 < len(articles) else len(text)
            article_text = text[start_pos:end_pos].strip()

            # Estimate tokens (rough: 1 token ≈ 4 chars for Ukrainian)
            tokens = len(article_text) / 4

            if tokens <= self.max_chunk_size:
                # Article fits in one chunk
                chunk = {
                    "text": article_text,
                    "article_number": int(article_num),
                    "article_title": article_title,
                    "tokens_approx": int(tokens),
                }

                # Extract metadata from context before article
                context_before = text[max(0, start_pos - 500) : start_pos]
                metadata = self._extract_metadata_from_context(context_before)
                chunk.update(metadata)

                chunks.append(chunk)
            else:
                # Article too long → split with overlap
                sub_chunks = self._split_long_article(article_text, article_num, article_title)
                chunks.extend(sub_chunks)

        return chunks

    def _split_long_article(
        self, article_text: str, article_num: str, article_title: str
    ) -> list[dict]:
        """Split long article into smaller chunks with overlap."""
        chunks = []

        # Split by paragraphs
        paragraphs = [p.strip() for p in article_text.split("\n\n") if p.strip()]

        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(para) / 4

            if current_tokens + para_tokens > self.target_chunk_size and current_chunk:
                # Create chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(
                    {
                        "text": chunk_text,
                        "article_number": int(article_num),
                        "article_title": article_title,
                        "part_of_long_article": True,
                        "tokens_approx": int(current_tokens),
                    }
                )

                # Overlap: keep last paragraph
                if self.overlap_percent > 0:
                    overlap_paras = int(len(current_chunk) * self.overlap_percent)
                    current_chunk = current_chunk[-max(1, overlap_paras) :]
                    current_tokens = sum(len(p) / 4 for p in current_chunk)
                else:
                    current_chunk = []
                    current_tokens = 0

            current_chunk.append(para)
            current_tokens += para_tokens

        # Add last chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(
                {
                    "text": chunk_text,
                    "article_number": int(article_num),
                    "article_title": article_title,
                    "part_of_long_article": True,
                    "tokens_approx": int(current_tokens),
                }
            )

        return chunks

    def _chunk_by_size(self, text: str, pages_info: list[dict]) -> list[dict]:
        """Fallback: chunk by size when no structure detected."""
        chunks = []

        # Split by double newlines (paragraphs)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        current_chunk = []
        current_tokens = 0
        chunk_index = 0

        for para in paragraphs:
            para_tokens = len(para) / 4

            if current_tokens + para_tokens > self.target_chunk_size and current_chunk:
                # Create chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(
                    {
                        "text": chunk_text,
                        "chunk_type": "size_based",
                        "chunk_index": chunk_index,
                        "tokens_approx": int(current_tokens),
                    }
                )
                chunk_index += 1

                # Overlap
                if self.overlap_percent > 0:
                    overlap_paras = int(len(current_chunk) * self.overlap_percent)
                    current_chunk = current_chunk[-max(1, overlap_paras) :]
                    current_tokens = sum(len(p) / 4 for p in current_chunk)
                else:
                    current_chunk = []
                    current_tokens = 0

            current_chunk.append(para)
            current_tokens += para_tokens

        # Add last chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(
                {
                    "text": chunk_text,
                    "chunk_type": "size_based",
                    "chunk_index": chunk_index,
                    "tokens_approx": int(current_tokens),
                }
            )

        return chunks

    def _extract_metadata_from_context(self, context: str) -> dict:
        """Extract Book/Section/Chapter from context before article."""
        metadata = {
            "book": None,
            "book_number": None,
            "section": None,
            "section_number": None,
            "chapter": None,
            "chapter_number": None,
        }

        # Try Ukrainian patterns
        book_match = self.PATTERNS["book"].search(context)
        if book_match:
            metadata["book"] = book_match.group(0).strip()
            metadata["book_number"] = self._extract_number(book_match.group(1))

        section_match = self.PATTERNS["section"].search(context)
        if section_match:
            metadata["section"] = section_match.group(0).strip()
            metadata["section_number"] = self._extract_number(section_match.group(1))

        chapter_match = self.PATTERNS["chapter"].search(context)
        if chapter_match:
            metadata["chapter"] = chapter_match.group(0).strip()
            metadata["chapter_number"] = self._extract_number(chapter_match.group(1))

        # Try Russian patterns if nothing found
        if not metadata["book"]:
            book_match = self.PATTERNS["book_ru"].search(context)
            if book_match:
                metadata["book"] = book_match.group(0).strip()
                metadata["book_number"] = self._extract_number(book_match.group(1))

        if not metadata["section"]:
            section_match = self.PATTERNS["section_ru"].search(context)
            if section_match:
                metadata["section"] = section_match.group(0).strip()
                metadata["section_number"] = self._extract_number(section_match.group(1))

        if not metadata["chapter"]:
            chapter_match = self.PATTERNS["chapter_ru"].search(context)
            if chapter_match:
                metadata["chapter"] = chapter_match.group(0).strip()
                metadata["chapter_number"] = self._extract_number(chapter_match.group(1))

        return metadata

    def _extract_number(self, text: str) -> int:
        """Extract number from text (arabic, roman, or words)."""
        # Try arabic number first
        number_match = re.search(r"\d+", text)
        if number_match:
            return int(number_match.group())

        # Try roman numerals
        roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        if all(c in roman_map for c in text.upper()):
            return self._roman_to_int(text.upper())

        # Try word numbers (Ukrainian/Russian)
        word_numbers = {
            "перша": 1,
            "перший": 1,
            "первая": 1,
            "первый": 1,
            "друга": 2,
            "другий": 2,
            "вторая": 2,
            "второй": 2,
            "третя": 3,
            "третій": 3,
            "третья": 3,
            "третий": 3,
            "четверта": 4,
            "четвертий": 4,
            "четвертая": 4,
            "четвертый": 4,
            "п'ята": 5,
            "п'ятий": 5,
            "пятая": 5,
            "пятый": 5,
        }

        text_lower = text.lower()
        for word, num in word_numbers.items():
            if word in text_lower:
                return num

        return None

    def _roman_to_int(self, s: str) -> int:
        """Convert Roman numeral to integer."""
        roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        result = 0
        prev_value = 0

        for char in reversed(s):
            value = roman_map[char]
            if value < prev_value:
                result -= value
            else:
                result += value
            prev_value = value

        return result


# Quick test
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 pymupdf_chunker.py <pdf_file>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print(f"Chunking: {pdf_path}")
    chunker = PyMuPDFChunker()
    chunks = chunker.chunk_pdf(pdf_path)

    print(f"\nTotal chunks: {len(chunks)}")
    print("\nFirst 3 chunks:")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n--- Chunk {i + 1} ---")
        print(f"Text: {chunk['text'][:200]}...")
        print(f"Metadata: {[k for k, v in chunk.items() if k != 'text' and v is not None]}")
