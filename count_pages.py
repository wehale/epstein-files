#!/usr/bin/env python3
"""Count pages in all downloaded PDFs and update manifest.json.

Requirements: pip install pypdf
"""

import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf is required. Install with: pip install pypdf")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
DOC_DIR = SCRIPT_DIR / "documents"
MANIFEST_FILE = SCRIPT_DIR / "manifest.json"


def main():
    if not MANIFEST_FILE.exists():
        print("ERROR: manifest.json not found. Run download.py first.")
        sys.exit(1)

    manifest = json.loads(MANIFEST_FILE.read_text())
    print(f"Manifest: {len(manifest)} entries")

    # Build lookup by filename
    by_name = {entry["filename"]: entry for entry in manifest}

    # Also pick up any PDFs not in the manifest
    on_disk = set(f.name for f in DOC_DIR.glob("*.pdf"))
    in_manifest = set(by_name.keys())
    orphans = on_disk - in_manifest
    if orphans:
        print(f"  {len(orphans)} files on disk not in manifest — adding them")
        for name in sorted(orphans):
            by_name[name] = {
                "filename": name,
                "source": "unknown",
                "source_url": "",
                "md5": "",
                "size_bytes": (DOC_DIR / name).stat().st_size,
            }

    total_pages = 0
    errors = 0
    already_counted = 0

    files = sorted(by_name.keys())
    for i, filename in enumerate(files, 1):
        entry = by_name[filename]
        if entry.get("pages") and entry["pages"] > 0:
            total_pages += entry["pages"]
            already_counted += 1
            continue

        path = DOC_DIR / filename
        if not path.exists():
            continue

        try:
            reader = PdfReader(path)
            pages = len(reader.pages)
            entry["pages"] = pages
            total_pages += pages
        except Exception:
            entry["pages"] = 0
            entry["error"] = "unreadable"
            errors += 1

        if i % 200 == 0:
            print(f"  [{i}/{len(files)}] {total_pages:,} pages so far...")

    # Detect Bates numbers
    for entry in by_name.values():
        name = entry["filename"]
        match = __import__("re").match(r'^(EFTA\d+)', name)
        if match:
            entry["bates_number"] = match.group(1)

    # Write updated manifest
    manifest = sorted(by_name.values(), key=lambda f: f["filename"])
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))

    # Stats
    doc_count = len([e for e in manifest if e.get("pages", 0) > 0])
    total_size = sum(e.get("size_bytes", 0) for e in manifest)

    print(f"\n{'='*50}")
    print(f"  Documents:    {doc_count:,}")
    print(f"  Total pages:  {total_pages:,}")
    print(f"  Total size:   {total_size / 1e9:.1f} GB")
    print(f"  Errors:       {errors}")
    if already_counted:
        print(f"  Already had page counts: {already_counted}")
    print(f"{'='*50}")

    # Cost estimate
    textract_cost = total_pages * 0.015
    summary_cost = doc_count * 0.05
    embed_cost = doc_count * 0.003
    total_cost = textract_cost + summary_cost + embed_cost
    print(f"\n  Estimated ingestion cost (AWS Textract + Bedrock):")
    print(f"    Textract OCR:  ${textract_cost:,.2f}")
    print(f"    Summarization: ${summary_cost:,.2f}")
    print(f"    Embeddings:    ${embed_cost:,.2f}")
    print(f"    Total:         ${total_cost:,.2f}")


if __name__ == "__main__":
    main()
