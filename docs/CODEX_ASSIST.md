# Optional Codex Assist

Codex can generate conservative curator-assist notes from local papers and pipeline outputs.

Codex output is optional and assistive only.

## Run selected PMIDs

    ./scripts/24_run_codex_curator_assist_selected.sh "31737630,32552779"

## Merge Codex notes

    python scripts/25_merge_codex_curator_assist.py

## Important rule

Codex should not modify parser scripts or metadata tables.

It should only write:

    outputs/PMID_<PMID>_codex_curator_assist.md
    outputs/PMID_<PMID>_codex_group_suggestions.tsv

Curators make final decisions.
