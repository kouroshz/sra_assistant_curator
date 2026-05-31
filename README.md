# SRA Paper Curator

Goal: build a simple assistant-curator workflow for PMID-linked Plasmodium sequencing metadata.

Given:
- a PMID
- the master SRA metadata sheet
- a local paper PDF

The workflow will:
1. find SRR rows associated with the PMID
2. read/summarize the paper
3. populate Shalini-style curated metadata fields
4. assign likely controls when possible
5. flag uncertain rows for human review

The agent does not download new data or add missing SRRs.
It only curates rows already present in the master metadata table.
