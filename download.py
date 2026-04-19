#!/usr/bin/env python3
"""Download the complete Epstein/Maxwell public document collection.

Pulls from Archive.org mirrors of DOJ releases, RECAP federal court
filings, and FBI FOIA releases. Deduplicates by MD5 hash. Resumable —
tracks progress in documents/.download_progress.json.

Requirements: pip install httpx
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "documents"
PROGRESS_FILE = OUTPUT_DIR / ".download_progress.json"
MANIFEST_FILE = SCRIPT_DIR / "manifest.json"

SKIP_SUFFIXES = ("_text.pdf", "_chocr.html.gz", "_djvu.txt", "_djvu.xml",
                 "_jp2.zip", "_daisy.zip", "_abbyy.gz", "_marc.xml",
                 "_meta.xml", "_files.xml", "_meta.sqlite")
MAX_FILE_SIZE_MB = 200


# ── Sources ──────────────────────────────────────────────────────────

DOJ_ZIPS = [
    ("https://archive.org/download/data-set-1/DataSet%201.zip", "DOJ Dataset 1", 1200),
    ("https://archive.org/download/data-set-1/DataSet%202.zip", "DOJ Dataset 2", 600),
    ("https://archive.org/download/data-set-1/DataSet%203.zip", "DOJ Dataset 3", 600),
    ("https://archive.org/download/data-set-1/DataSet%204.zip", "DOJ Dataset 4", 600),
    ("https://archive.org/download/data-set-1/DataSet%205.zip", "DOJ Dataset 5", 300),
    ("https://archive.org/download/data-set-1/DataSet%206.zip", "DOJ Dataset 6", 300),
    ("https://archive.org/download/data-set-1/DataSet%207.zip", "DOJ Dataset 7", 300),
    ("https://archive.org/download/epstein-files_202512/DataSet%208.zip", "DOJ Dataset 8", 3600),
    ("https://archive.org/download/data-set-12_202601/DataSet%2012.zip", "DOJ Dataset 12", 300),
]

RECAP_CASES = [
    ("gov.uscourts.nysd.447706", "Giuffre v. Maxwell (15-cv-07433)"),
    ("gov.uscourts.nysd.539612", "US v. Maxwell (20-cr-330)"),
    ("gov.uscourts.nysd.539611", "US v. Epstein (19-cr-490)"),
    ("gov.uscourts.nysd.518648", "US v. Epstein (related #1)"),
    ("gov.uscourts.nysd.518649", "US v. Epstein (related #2)"),
]

ARCHIVE_COLLECTIONS = [
    ("epstein-docs_20240108", "Curated court docs & depositions"),
    ("epstein-doj-datasets-9-11-jan2026", "DOJ Datasets 9-11 index"),
    ("data-set-12-doj", "DOJ Dataset 12 individual PDFs"),
    ("epsteindocs", "Epstein case documents"),
    ("epstein-docs", "Epstein appeals docs"),
]

FBI_VAULT_ITEM = "jeffrey-epstein-FBI-vault-files"


# ── Helpers ──────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"completed_sources": [], "files": {}}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def hash_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def clean_filename(name: str) -> str:
    name = unquote(name)
    name = name.replace(" ", "_").replace("'", "").replace(",", "")
    name = re.sub(r'[^\w\-_.]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    return name


def download_pdf(url: str, dest: Path, timeout: int = 120) -> bool:
    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"  FAIL: {dest.name}: {e}")
        if dest.exists():
            dest.unlink()
        return False


def download_and_extract_zip(url: str, dest_dir: Path, hashes: set[str],
                              source: str, label: str,
                              timeout: int = 600) -> list[dict]:
    """Download a zip, extract PDFs, deduplicate. Returns file metadata."""
    new_files = []
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        print(f"  Downloading {label}...")
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            last_report = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=262144):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and downloaded - last_report > 50_000_000:
                        pct = downloaded / total * 100
                        print(f"    {downloaded / 1e6:.0f} / {total / 1e6:.0f} MB ({pct:.0f}%)")
                        last_report = downloaded
            print(f"    Downloaded {downloaded / 1e6:.0f} MB")

        print(f"  Extracting PDFs...")
        try:
            with zipfile.ZipFile(tmp_path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    basename = Path(info.filename).name
                    if not basename.lower().endswith('.pdf'):
                        continue
                    if any(basename.lower().endswith(s) for s in SKIP_SUFFIXES):
                        continue
                    if info.file_size < 100:
                        continue
                    if info.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                        continue

                    clean = clean_filename(basename)
                    dest = dest_dir / clean
                    if dest.exists():
                        continue

                    data = zf.read(info)
                    h = hash_bytes(data)
                    if h in hashes:
                        continue

                    dest.write_bytes(data)
                    hashes.add(h)
                    new_files.append({
                        "filename": clean,
                        "source": source,
                        "source_url": url,
                        "md5": h,
                        "size_bytes": len(data),
                    })
        except zipfile.BadZipFile:
            print(f"    WARNING: Bad zip file for {label}")
    finally:
        tmp_path.unlink(missing_ok=True)

    print(f"    {len(new_files)} new PDFs from {label}")
    return new_files


def fetch_archive_org_pdfs(item_id: str) -> list[dict]:
    url = f"https://archive.org/metadata/{item_id}"
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    files = data.get("files", [])
    pdfs = []
    for f in files:
        name = f["name"]
        if not name.lower().endswith(".pdf"):
            continue
        if any(name.lower().endswith(s) for s in SKIP_SUFFIXES):
            continue
        size = int(f.get("size", 0))
        if size > MAX_FILE_SIZE_MB * 1024 * 1024 or size < 100:
            continue
        encoded_name = quote(name, safe="")
        pdfs.append({
            "url": f"https://archive.org/download/{item_id}/{encoded_name}",
            "filename": name,
            "size": size,
        })
    return pdfs


def download_archive_org_pdfs(item_id: str, source: str, label: str,
                                dest_dir: Path, hashes: set[str]) -> list[dict]:
    pdfs = fetch_archive_org_pdfs(item_id)
    print(f"  Found {len(pdfs)} PDFs in {label}")

    new_files = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for pdf in pdfs:
            clean = clean_filename(pdf["filename"])
            dest = dest_dir / clean
            if dest.exists():
                continue
            futures[executor.submit(download_pdf, pdf["url"], dest)] = (pdf, clean, dest)

        for i, future in enumerate(as_completed(futures), 1):
            pdf, clean, dest = futures[future]
            if future.result() and dest.exists():
                h = hash_file(dest)
                if h in hashes:
                    dest.unlink()
                else:
                    hashes.add(h)
                    new_files.append({
                        "filename": clean,
                        "source": source,
                        "source_url": pdf["url"],
                        "md5": h,
                        "size_bytes": dest.stat().st_size,
                    })
            if i % 100 == 0:
                print(f"    Progress: {i}/{len(futures)} checked, {len(new_files)} new")

    print(f"    {len(new_files)} new PDFs from {label}")
    return new_files


# ── Main ─────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    print("=" * 70)
    print("  Epstein/Maxwell Complete Document Collection")
    print("  https://github.com/yourusername/epstein-files")
    print("=" * 70)

    # Build dedup index from existing downloads
    print("\nIndexing existing files for deduplication...")
    hashes: set[str] = set()
    for f in OUTPUT_DIR.glob("*.pdf"):
        hashes.add(hash_file(f))
    print(f"  {len(hashes)} existing documents")

    all_file_metadata: list[dict] = list(progress.get("files", {}).values())

    # ── DOJ Dataset zips ──
    for url, label, timeout in DOJ_ZIPS:
        source_key = f"doj_zip:{label}"
        if source_key in progress["completed_sources"]:
            print(f"\n  [skip] {label} (already completed)")
            continue
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        new = download_and_extract_zip(url, OUTPUT_DIR, hashes,
                                        source=label, label=label, timeout=timeout)
        all_file_metadata.extend(new)
        progress["completed_sources"].append(source_key)
        for f in new:
            progress["files"][f["filename"]] = f
        save_progress(progress)

    # ── RECAP court filings ──
    for item_id, label in RECAP_CASES:
        source_key = f"recap:{item_id}"
        if source_key in progress["completed_sources"]:
            print(f"\n  [skip] {label} (already completed)")
            continue
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"  archive.org/details/{item_id}")
        print(f"{'='*60}")
        new = download_archive_org_pdfs(item_id, source=label, label=label,
                                         dest_dir=OUTPUT_DIR, hashes=hashes)
        all_file_metadata.extend(new)
        progress["completed_sources"].append(source_key)
        for f in new:
            progress["files"][f["filename"]] = f
        save_progress(progress)

    # ── FBI Vault ──
    source_key = "fbi_vault"
    if source_key not in progress["completed_sources"]:
        print(f"\n{'='*60}")
        print(f"  FBI Vault FOIA Release (22 parts)")
        print(f"{'='*60}")
        new = download_archive_org_pdfs(FBI_VAULT_ITEM, source="FBI Vault FOIA",
                                         label="FBI Vault", dest_dir=OUTPUT_DIR,
                                         hashes=hashes)
        all_file_metadata.extend(new)
        progress["completed_sources"].append(source_key)
        for f in new:
            progress["files"][f["filename"]] = f
        save_progress(progress)

    # ── Archive.org curated collections ──
    for item_id, label in ARCHIVE_COLLECTIONS:
        source_key = f"archive:{item_id}"
        if source_key in progress["completed_sources"]:
            print(f"\n  [skip] {label} (already completed)")
            continue
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"  archive.org/details/{item_id}")
        print(f"{'='*60}")
        new = download_archive_org_pdfs(item_id, source=label, label=label,
                                         dest_dir=OUTPUT_DIR, hashes=hashes)
        all_file_metadata.extend(new)
        progress["completed_sources"].append(source_key)
        for f in new:
            progress["files"][f["filename"]] = f
        save_progress(progress)

    # ── Write manifest ──
    manifest = sorted(progress["files"].values(), key=lambda f: f["filename"])
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))

    # ── Summary ──
    total_pdfs = list(OUTPUT_DIR.glob("*.pdf"))
    total_size = sum(f.stat().st_size for f in total_pdfs)

    print(f"\n{'='*70}")
    print(f"  DOWNLOAD COMPLETE")
    print(f"{'='*70}")
    print(f"  Total PDFs: {len(total_pdfs)}")
    print(f"  Total size: {total_size / 1e9:.1f} GB")
    print(f"  Manifest:   {MANIFEST_FILE}")
    print(f"  Documents:  {OUTPUT_DIR}")
    print(f"\n  Sources:")
    for s in progress["completed_sources"]:
        print(f"    + {s}")
    print(f"\n  Run count_pages.py to add page counts to the manifest.")


if __name__ == "__main__":
    main()
