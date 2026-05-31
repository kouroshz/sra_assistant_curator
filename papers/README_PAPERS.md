# Papers Directory

Place local paper PDFs here.

PDF files are not tracked by Git.

## Recommended filename format

    <PMID>_<short_title>.pdf

Example:

    31737630_TRIBE_Uncovers_RNA_Targets_of_Rrp6.pdf

The PMID prefix helps the pipeline match papers to metadata rows.

## How to get PDFs

There are two options.

### Option A: use the open-access downloader

After creating the PMID list, run:

    python scripts/15_download_open_access_pdfs.py \
      --pmids-file outputs/pmids_needing_pdfs.tsv \
      --email YOUR_EMAIL_HERE \
      --sleep 1.0

The downloader attempts open-access sources such as PubMed/PMC/Europe PMC/publisher PDF links.

It will not find every PDF.

### Option B: download manually

Manually download remaining papers and put the PDFs in this folder.

Institutional access may be needed for some papers.

## Do not commit PDFs

PDFs are local working files and should not be committed to Git.
