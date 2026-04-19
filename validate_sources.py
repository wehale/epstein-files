#!/usr/bin/env python3
"""Validate that all document sources are still reachable and intact.

Checks every Archive.org item and zip URL used by download.py:
  - Items exist and return metadata
  - PDF file counts match expected minimums (catches silent removals)
  - Zip files are reachable and sizes match expected values (catches corruption/replacement)

Intended to run as a weekly GitHub Action — if a source degrades,
the workflow fails and opens an issue.

Exit code 0 = all sources OK, 1 = one or more problems detected.
"""

import sys
import httpx

# Archive.org items — expected minimum PDF counts.
# We use minimums (not exact) so new files being added doesn't trigger a failure.
# If the actual count drops below the minimum, something was removed.
ARCHIVE_ORG_ITEMS = [
    # (item_id, label, min_pdf_count)
    ("data-set-1", "DOJ Datasets 1-7 mirror", 1),
    ("epstein-files_202512", "DOJ Dataset 8 mirror", 0),
    ("data-set-12_202601", "DOJ Dataset 12 mirror", 0),
    ("gov.uscourts.nysd.447706", "Giuffre v. Maxwell (RECAP)", 1900),
    ("gov.uscourts.nysd.539612", "US v. Maxwell (RECAP)", 1080),
    ("gov.uscourts.nysd.539611", "US v. Epstein (RECAP)", 90),
    ("gov.uscourts.nysd.518648", "US v. Epstein related #1 (RECAP)", 40),
    ("gov.uscourts.nysd.518649", "US v. Epstein related #2 (RECAP)", 120),
    ("jeffrey-epstein-FBI-vault-files", "FBI Vault FOIA", 20),
    ("epstein-docs_20240108", "Curated court docs", 5),
    ("epstein-doj-datasets-9-11-jan2026", "DOJ Datasets 9-11 index", 1),
    ("data-set-12-doj", "DOJ Dataset 12 individual PDFs", 1),
    ("epsteindocs", "Epstein case documents", 1),
    ("epstein-docs", "Epstein appeals docs", 1),
]

# Zip download URLs — expected sizes in bytes (10% tolerance).
# Size of 0 means we only check reachability, not size.
ZIP_URLS = [
    # (url, label, expected_bytes)
    ("https://archive.org/download/data-set-1/DataSet%201.zip", "DOJ Dataset 1", 1_315_000_000),
    ("https://archive.org/download/data-set-1/DataSet%202.zip", "DOJ Dataset 2", 661_000_000),
    ("https://archive.org/download/data-set-1/DataSet%203.zip", "DOJ Dataset 3", 625_000_000),
    ("https://archive.org/download/data-set-1/DataSet%204.zip", "DOJ Dataset 4", 369_000_000),
    ("https://archive.org/download/data-set-1/DataSet%205.zip", "DOJ Dataset 5", 64_000_000),
    ("https://archive.org/download/data-set-1/DataSet%206.zip", "DOJ Dataset 6", 54_000_000),
    ("https://archive.org/download/data-set-1/DataSet%207.zip", "DOJ Dataset 7", 102_000_000),
    ("https://archive.org/download/epstein-files_202512/DataSet%208.zip", "DOJ Dataset 8", 10_688_000_000),
    ("https://archive.org/download/data-set-12_202601/DataSet%2012.zip", "DOJ Dataset 12", 120_000_000),
]

SIZE_TOLERANCE = 0.10  # 10% — Archive.org occasionally recompresses


def check_archive_items() -> tuple[int, list[str]]:
    passed = 0
    failed = []
    warnings = []

    print("Validating Archive.org items...")
    for item_id, label, min_pdfs in ARCHIVE_ORG_ITEMS:
        url = f"https://archive.org/metadata/{item_id}"
        try:
            r = httpx.get(url, timeout=30, follow_redirects=True)
            if r.status_code != 200:
                msg = f"{label} ({item_id}): HTTP {r.status_code}"
                print(f"  FAIL  {msg}")
                failed.append(msg)
                continue

            data = r.json()
            files = data.get("files", [])
            total_files = len(files)
            pdf_count = len([
                f for f in files
                if f["name"].lower().endswith(".pdf")
                and not f["name"].lower().endswith("_text.pdf")
            ])

            if min_pdfs > 0 and pdf_count < min_pdfs:
                msg = (f"{label} ({item_id}): PDF count dropped — "
                       f"expected >= {min_pdfs}, found {pdf_count}")
                print(f"  FAIL  {msg}")
                failed.append(msg)
            else:
                print(f"  OK    {label} — {pdf_count} PDFs, {total_files} total files")
                passed += 1

        except Exception as e:
            msg = f"{label} ({item_id}): {e}"
            print(f"  FAIL  {msg}")
            failed.append(msg)

    return passed, failed


def check_zip_urls() -> tuple[int, list[str]]:
    passed = 0
    failed = []

    print("\nValidating zip download URLs...")
    for url, label, expected_bytes in ZIP_URLS:
        try:
            r = httpx.head(url, timeout=30, follow_redirects=True)
            if r.status_code not in (200, 302):
                msg = f"{label}: HTTP {r.status_code}"
                print(f"  FAIL  {msg}")
                failed.append(msg)
                continue

            actual_size = int(r.headers.get("content-length", 0))

            if expected_bytes > 0 and actual_size > 0:
                ratio = actual_size / expected_bytes
                if abs(1 - ratio) > SIZE_TOLERANCE:
                    msg = (f"{label}: size changed — "
                           f"expected ~{expected_bytes/1e6:.0f} MB, "
                           f"got {actual_size/1e6:.0f} MB "
                           f"({ratio:.0%} of expected)")
                    print(f"  WARN  {msg}")
                    failed.append(msg)
                else:
                    print(f"  OK    {label} — {actual_size/1e6:.0f} MB (within tolerance)")
                    passed += 1
            elif actual_size > 0:
                print(f"  OK    {label} — {actual_size/1e6:.0f} MB")
                passed += 1
            else:
                print(f"  OK    {label} — reachable (size not in headers)")
                passed += 1

        except Exception as e:
            msg = f"{label}: {e}"
            print(f"  FAIL  {msg}")
            failed.append(msg)

    return passed, failed


def main():
    items_passed, items_failed = check_archive_items()
    zips_passed, zips_failed = check_zip_urls()

    total_passed = items_passed + zips_passed
    all_failed = items_failed + zips_failed

    print(f"\n{'='*60}")
    print(f"  Checks passed:  {total_passed}")
    print(f"  Checks failed:  {len(all_failed)}")
    print(f"{'='*60}")

    if all_failed:
        print("\nProblems detected:")
        for f in all_failed:
            print(f"  - {f}")
        print("\nUpdate download.py and validate_sources.py if sources moved.")
        sys.exit(1)
    else:
        print("\nAll sources verified — reachable, file counts stable, sizes match.")
        sys.exit(0)


if __name__ == "__main__":
    main()
