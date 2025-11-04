"""
Quick test for UniversalDocumentParser.

Tests all supported formats:
- PDF (CK.pdf)
- DOCX (CK.docx)
- CSV (demo_BG.csv)
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion import UniversalDocumentParser


def test_parser():
    """Test parser on all formats."""
    parser = UniversalDocumentParser(use_cache=True)

    test_files = [
        ("/srv/CK.pdf", "PDF"),
        ("/srv/CK.docx", "DOCX"),
        ("/srv/app/demo_BG.csv", "CSV"),
    ]

    print("=" * 70)
    print("UNIVERSAL DOCUMENT PARSER TEST")
    print("=" * 70)

    for filepath, format_name in test_files:
        filepath = Path(filepath)

        if not filepath.exists():
            print(f"\n❌ {format_name}: File not found - {filepath}")
            continue

        print(f"\n📄 {format_name}: {filepath.name}")
        print(f"   Size: {filepath.stat().st_size / 1024:.1f} KB")

        try:
            doc = parser.parse_file(filepath)

            print("   ✅ Parsed successfully")
            print(f"   Title: {doc.title}")
            print(f"   Content length: {len(doc.content):,} chars")
            print(f"   Metadata: {doc.metadata}")

            # Show preview
            preview = doc.content[:200].replace("\n", " ")
            print(f"   Preview: {preview}...")

        except Exception as e:
            print(f"   ❌ Failed: {e}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    test_parser()
