#!/usr/bin/env bash
set -euo pipefail

PMIDS="${1:-31737630,32552779,34365503,35288749,37833314}"

mkdir -p outputs/codex_logs
mkdir -p outputs/codex_prompts

IFS=',' read -ra PMID_ARRAY <<< "$PMIDS"

for PMID in "${PMID_ARRAY[@]}"; do
  PMID="$(echo "$PMID" | xargs)"
  echo
  echo "=== Codex curator assist for PMID ${PMID} ==="

  PROMPT_FILE="outputs/codex_prompts/PMID_${PMID}_codex_prompt.txt"
  LOG_FILE="outputs/codex_logs/PMID_${PMID}_codex.log"

  if [[ -s "outputs/PMID_${PMID}_codex_curator_assist.md" && -s "outputs/PMID_${PMID}_codex_group_suggestions.tsv" ]]; then
    echo "Codex outputs already exist for PMID ${PMID}; skipping."
    continue
  fi

  cat > "$PROMPT_FILE" <<EOF
We are in the local repo:

~/work/Parasites/code/sra_paper_curator

Task:
Create conservative curator-assist notes for PMID ${PMID}.

Important:
- Do NOT modify parser scripts.
- Do NOT modify master metadata.
- Do NOT overwrite existing curated outputs except the two Codex-assist output files listed below.
- You may inspect local PDFs, TSVs, Excel workbooks, and paper text files.
- You may run read-only shell/Python commands to inspect files.
- Do not hallucinate. If something is not explicitly supported by paper or metadata, write "needs curator confirmation."
- Your job is to help human curators, not to make final decisions.

Relevant local files to inspect if present:
- papers/*${PMID}*.pdf
- outputs/PMID_${PMID}_paper_text.txt
- outputs/PMID_${PMID}_paper_context.json
- outputs/PMID_${PMID}_paper_context_evidence.tsv
- outputs/PMID_${PMID}_agent_filled_master_rows_with_paper_context.tsv
- outputs/PMID_${PMID}_curator_review_view.xlsx
- outputs/curator_group_level_review_index.tsv
- outputs/curator_group_level_review_index.xlsx
- outputs/curator_review_index.tsv

Output files to write:
1. outputs/PMID_${PMID}_codex_curator_assist.md
2. outputs/PMID_${PMID}_codex_group_suggestions.tsv

Markdown file should contain:
# PMID ${PMID} curator assist

## 1. Paper-level experimental design summary
Briefly summarize the biological experiment and sequencing assay.

## 2. Main sample groups
List major groups from the current group-level metadata.

## 3. Likely controls/comparisons
Describe likely controls and comparisons. Be explicit about what is paper-supported versus inferred.

## 4. Assessment of current group-level metadata
Say whether the current metadata/grouping looks:
- consistent
- mostly consistent with caveats
- problematic
- needs special handling

## 5. Ambiguities requiring human curator confirmation
List only real ambiguities.

## 6. Recommended curator actions
Give concrete actions for the curator.

TSV file columns must be exactly:
PMID
group_description
current_interpretation
codex_suggestion
confidence
evidence_from_paper
curator_action

Rules for TSV:
- One row per major biological/sample group or group type.
- confidence must be one of: high, medium, low.
- evidence_from_paper should be concise and source-grounded.
- curator_action should be practical, e.g. "PASS", "confirm comparator", "separate WT GlcN control", "needs paper review", "possible parser patch".
- Do not invent sample groups.
- Do not fabricate evidence.
EOF

  echo "Prompt written: $PROMPT_FILE"

  # Run Codex non-interactively.
  # If codex exec fails in your setup, run: codex
  # and paste the prompt file contents manually.
  codex exec --skip-git-repo-check --sandbox workspace-write "$(cat "$PROMPT_FILE")" > "$LOG_FILE" 2>&1 || {
    echo "Codex failed for PMID ${PMID}. See $LOG_FILE"
    continue
  }

  echo "Codex done for PMID ${PMID}"
  echo "Log: $LOG_FILE"
  echo "Expected outputs:"
  echo "  outputs/PMID_${PMID}_codex_curator_assist.md"
  echo "  outputs/PMID_${PMID}_codex_group_suggestions.tsv"
done
