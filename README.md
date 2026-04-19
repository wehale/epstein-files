# epstein-files

A script that downloads every publicly available document from the Epstein/Maxwell federal investigations, court proceedings, and FOIA releases. No PDFs are stored in this repo — the script pulls them from their original public sources (Archive.org, DOJ mirrors) and verifies checksums.

## What's included

| Source | Documents | Description |
|--------|-----------|-------------|
| DOJ Datasets 1-8, 12 | ~2,500+ | Official DOJ disclosures under the Epstein Files Transparency Act (Nov 2025). FBI 302 interview reports, investigation files, exhibits, Bates-numbered EFTA production. |
| Giuffre v. Maxwell (15-cv-07433) | ~1,900 | Civil case court filings: depositions, exhibits, the January 2024 unsealed batch, motions, orders. |
| US v. Maxwell (20-cr-330) | ~1,080 | Criminal prosecution: indictment, trial exhibits, sentencing memoranda, appeals. |
| US v. Epstein (19-cr-490) | ~250 | Criminal case filings, bail memo, indictment, related proceedings. |
| FBI Vault FOIA | 22 | FBI's FOIA release (Parts 1-22) of investigative files. |
| Archive.org collections | ~100 | Curated compilations: flight logs, black book, plea deal, asset disclosures. |

## What's NOT included

- **DOJ Datasets 9-11** (~287 GB) — too large for practical download. These contain bulk scan images. Available via torrent from Archive.org.
- **House Oversight Committee releases** (~53,000 pages) — partially available as text extracts on Archive.org but not yet as downloadable PDFs.
- **Sealed documents** — anything not publicly released by a court or government agency.
- **Secondary sources** — no books, journalism, or commentary. Primary documents only.

## Usage

```bash
# Install dependencies
pip install httpx

# Download everything (~16 GB, takes 1-2 hours)
python download.py

# Download is resumable — rerun if interrupted
python download.py

# Count pages after download
python count_pages.py
```

Documents are downloaded into `documents/` and deduplicated by MD5 hash. The `manifest.json` file lists every document with its source URL, checksum, and page count.

## Manifest format

```json
{
  "filename": "EFTA00039025.pdf",
  "source": "DOJ Dataset 1",
  "source_url": "https://archive.org/download/data-set-1/DataSet%201.zip",
  "pages": 12,
  "size_bytes": 245832,
  "md5": "a1b2c3d4e5f6...",
  "bates_number": "EFTA00039025"
}
```

## Provenance

Every file in this collection is traceable to a public government release or federal court filing. Sources:

- **DOJ**: [justice.gov/epstein](https://www.justice.gov/epstein/doj-disclosures) (mirrored on Archive.org)
- **RECAP/CourtListener**: Federal court PACER filings archived at [archive.org](https://archive.org)
- **FBI Vault**: [vault.fbi.gov/jeffrey-epstein](https://vault.fbi.gov/jeffrey-epstein) (mirrored on Archive.org)

## Why this exists

These are public records released by the US government and federal courts. They should be easy to access, verify, and search. This repo makes the collection reproducible — anyone can run the script and get the same set of documents, verified by checksum.

## License

The documents themselves are US government works and federal court filings — public domain. The scripts in this repo are MIT licensed.
