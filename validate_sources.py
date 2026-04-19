#!/usr/bin/env python3
"""Validate that all document sources are still reachable.

Checks every Archive.org item and zip URL used by download.py.
Intended to run as a weekly GitHub Action — if a source goes down,
the workflow fails and opens an issue.

Exit code 0 = all sources OK, 1 = one or more sources unreachable.
"""

import sys
import httpx

# Archive.org items — check metadata endpoint returns 200
ARCHIVE_ORG_ITEMS = [
    ("data-set-1", "DOJ Datasets 1-7 mirror"),
    ("epstein-files_202512", "DOJ Dataset 8 mirror"),
    ("data-set-12_202601", "DOJ Dataset 12 mirror"),
    ("gov.uscourts.nysd.447706", "Giuffre v. Maxwell (RECAP)"),
    ("gov.uscourts.nysd.539612", "US v. Maxwell (RECAP)"),
    ("gov.uscourts.nysd.539611", "US v. Epstein (RECAP)"),
    ("gov.uscourts.nysd.518648", "US v. Epstein related #1 (RECAP)"),
    ("gov.uscourts.nysd.518649", "US v. Epstein related #2 (RECAP)"),
    ("jeffrey-epstein-FBI-vault-files", "FBI Vault FOIA"),
    ("epstein-docs_20240108", "Curated court docs"),
    ("epstein-doj-datasets-9-11-jan2026", "DOJ Datasets 9-11 index"),
    ("data-set-12-doj", "DOJ Dataset 12 individual PDFs"),
    ("epsteindocs", "Epstein case documents"),
    ("epstein-docs", "Epstein appeals docs"),
]

# Zip download URLs — check with HEAD request
ZIP_URLS = [
    ("https://archive.org/download/data-set-1/DataSet%201.zip", "DOJ Dataset 1"),
    ("https://archive.org/download/data-set-1/DataSet%202.zip", "DOJ Dataset 2"),
    ("https://archive.org/download/data-set-1/DataSet%203.zip", "DOJ Dataset 3"),
    ("https://archive.org/download/data-set-1/DataSet%204.zip", "DOJ Dataset 4"),
    ("https://archive.org/download/data-set-1/DataSet%205.zip", "DOJ Dataset 5"),
    ("https://archive.org/download/data-set-1/DataSet%206.zip", "DOJ Dataset 6"),
    ("https://archive.org/download/data-set-1/DataSet%207.zip", "DOJ Dataset 7"),
    ("https://archive.org/download/epstein-files_202512/DataSet%208.zip", "DOJ Dataset 8"),
    ("https://archive.org/download/data-set-12_202601/DataSet%2012.zip", "DOJ Dataset 12"),
]


def main():
    failed = []
    passed = 0

    print("Validating Archive.org items...")
    for item_id, label in ARCHIVE_ORG_ITEMS:
        url = f"https://archive.org/metadata/{item_id}"
        try:
            r = httpx.get(url, timeout=30, follow_redirects=True)
            if r.status_code == 200:
                data = r.json()
                file_count = len(data.get("files", []))
                print(f"  OK  {label} ({item_id}) — {file_count} files")
                passed += 1
            else:
                print(f"  FAIL  {label} ({item_id}) — HTTP {r.status_code}")
                failed.append(f"{label} ({item_id}): HTTP {r.status_code}")
        except Exception as e:
            print(f"  FAIL  {label} ({item_id}) — {e}")
            failed.append(f"{label} ({item_id}): {e}")

    print("\nValidating zip download URLs...")
    for url, label in ZIP_URLS:
        try:
            r = httpx.head(url, timeout=30, follow_redirects=True)
            if r.status_code in (200, 302):
                size = int(r.headers.get("content-length", 0))
                if size > 0:
                    print(f"  OK  {label} — {size / 1e6:.0f} MB")
                else:
                    print(f"  OK  {label} — size unknown (redirect)")
                passed += 1
            else:
                print(f"  FAIL  {label} — HTTP {r.status_code}")
                failed.append(f"{label}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  FAIL  {label} — {e}")
            failed.append(f"{label}: {e}")

    print(f"\n{'='*50}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {len(failed)}")
    print(f"{'='*50}")

    if failed:
        print("\nFailed sources:")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nAll sources verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()
