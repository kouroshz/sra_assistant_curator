# Optional agentic AI Assist

agentic AI can generate conservative curator-assist notes from local papers and pipeline outputs.

agentic AI output is optional and assistive only.

## Run selected PMIDs

    ./scripts/24_run_agentic_ai_curator_assist_selected.sh "31737630,32552779"

## Merge agentic AI notes

    python scripts/25_merge_agentic_ai_curator_assist.py

## Important rule

agentic AI should not modify parser scripts or metadata tables.

It should only write:

    outputs/PMID_<PMID>_agentic_ai_curator_assist.md
    outputs/PMID_<PMID>_agentic_ai_group_suggestions.tsv

Curators make final decisions.
