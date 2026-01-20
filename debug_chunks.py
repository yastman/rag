***REMOVED***!/usr/bin/env python3
"""Debug chunking for CSV file."""

from pathlib import Path

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter


***REMOVED*** Convert CSV
file_path = Path("data/demo/demo_BG.csv")
doc_converter = DocumentConverter()
result = doc_converter.convert(file_path)
dl_doc = result.document

***REMOVED*** Export to markdown to see structure
md_content = dl_doc.export_to_markdown()
print("=" * 80)
print("MARKDOWN CONTENT:")
print("=" * 80)
print(md_content[:1000])
print("\n...")
print(md_content[-500:])
print()

***REMOVED*** Chunk with HybridChunker
chunker = HybridChunker(tokenizer="BAAI/bge-m3", max_tokens=512)
doc_chunks = list(chunker.chunk(dl_doc))

print("=" * 80)
print(f"CHUNKS: {len(doc_chunks)}")
print("=" * 80)

for i, chunk in enumerate(doc_chunks):
    print(f"\n--- Chunk {i + 1} ---")
    print(f"Length: {len(chunk.text)} chars")
    print("Content preview:")
    print(chunk.text[:300] + "..." if len(chunk.text) > 300 else chunk.text)
