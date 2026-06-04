#!/usr/bin/env python3

"""
Run optional API-based agentic curation on ONE trusted paper/BioProject packet.

This script:
  - requires AGENTIC_AI_ENABLE_API=1 unless --dry-run
  - reads one paper-level packet JSON
  - reads its sidecar rowwise evidence TSV
  - reads matched PDF text if available
  - adds assay-aware task context from trusted_assay_aware_ai_queue.tsv
  - writes prompt, raw response, parsed JSON, and audit files

It does NOT modify the master sheet.
It does NOT modify curator-approved fields.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_QUEUE = Path("outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv")
DEFAULT_PACKET_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_json")
DEFAULT_OUT_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
DEFAULT_MODEL = "gpt-5.4-mini"


OUTPUT_SCHEMA = {
    "packet_id": "string",
    "pmid": "string",
    "bioproject": "string",
    "ai_review_status": "reviewed | insufficient_evidence | skipped | error",
    "assay_class_confirmed": "rna_seq_expression_or_timecourse | rna_seq_contrast_or_perturbation | chip_like_target_enrichment | mixed_or_ambiguous | other_or_unknown",
    "study_summary": {
        "one_sentence_summary": "string",
        "study_goal": "string",
        "organism_strain": "string or unknown",
        "assay_types": ["strings"],
        "main_comparisons_or_sample_axes": ["strings"],
        "paper_evidence_locations": ["short locations: Methods/Table/Figure/page if available"],
    },
    "sample_map": [
        {
            "sample_class_id": "short stable label",
            "sample_class_description": "string",
            "matched_source_row_ids": ["ALL source_row_id values belonging to this real sample class; each source_row_id must appear in exactly one sample_map entry"],
            "matched_run_ids": ["ALL Run IDs belonging to this real sample class; must correspond to matched_source_row_ids"],
            "n_rows_matched": "integer",
            "assay_type": "string",
            "strain": "string or unknown",
            "stage_or_timepoint": "string or unknown",
            "condition": "string or unknown",
            "perturbation_or_treatment": "string or unknown",
            "target_or_antibody_or_tag": "string or not_applicable_or_unknown",
            "replicate_logic": "string or unknown",
            "sample_role": "expression_sample | perturbation_sample | control_sample | target_ip | input | IgG | untagged_control | mock | unknown",
            "suggested_comparator_or_background_class_id": "string or unknown or not_applicable",
            "analysis_ready_status": "expression_ready | deg_ready | deg_not_ready | peak_calling_ready | peak_calling_not_ready | partial | unknown",
            "blocker_reason": "string or none",
            "confidence": "high | medium | low",
            "evidence": "short evidence from paper and/or SRA/BioSample",
            "curator_check_priority": "high | medium | low",
            "warning_flags": ["strings"]
        }
    ],
    "rowwise_suggestions": [
        {
            "source_row_id": "string",
            "Run": "string",
            "sample_class_id": "string",
            "suggested_assay_type": "string",
            "suggested_stage_timepoint": "string or unknown",
            "suggested_strain": "string or unknown",
            "suggested_condition": "string or unknown",
            "suggested_perturbation_or_treatment": "string or unknown",
            "suggested_target_or_antibody_or_tag": "string or not_applicable_or_unknown",
            "suggested_sample_role": "string",
            "suggested_comparator_or_background": "string or unknown or not_applicable",
            "suggestion_confidence": "high | medium | low",
            "suggestion_evidence": "short string",
            "review_flag": "ok | curator_check | low_confidence | missing_background | missing_comparator | ambiguous"
        }
    ],
    "analysis_readiness": {
        "rna_expression_useful": "yes | no | partial | not_applicable | unknown",
        "rna_deg_ready": "yes | no | partial | not_applicable | unknown",
        "chip_peak_calling_ready": "yes | no | partial | not_applicable | unknown",
        "main_blockers": ["strings"]
    },
    "curator_priority": {
        "overall_priority": "high | medium | low",
        "top_questions_for_curator": ["strings"],
        "recommended_random_qc_rows": ["source_row_id values"]
    },
    "global_warnings": ["strings"]
}


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def safe_json_loads(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s.lower().startswith("json"):
            s = s[4:].strip()
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end + 1])
        raise


def extract_pdf_text(pdf_path: Path, max_chars: int = 120000) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:
        return f"[PDF extraction unavailable: {e}]"

    try:
        reader = PdfReader(str(pdf_path))
        chunks = []
        total = 0
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            txt = txt.strip()
            if txt:
                block = f"\n\n--- PDF page {i + 1} ---\n{txt}"
                chunks.append(block)
                total += len(block)
            if total >= max_chars:
                break
        out = "".join(chunks).strip()
        return out[:max_chars] if out else "[No text extracted from PDF.]"
    except Exception as e:
        return f"[PDF extraction failed: {pdf_path}: {e}]"


def choose_packet(args) -> Path:
    if args.packet_json:
        return Path(args.packet_json)

    if not args.packet_id:
        raise ValueError("Provide --packet-id or --packet-json.")

    candidate = args.packet_dir / f"{args.packet_id}.json"
    if not candidate.exists():
        raise FileNotFoundError(f"Could not find packet JSON: {candidate}")
    return candidate


def load_queue_row(queue_path: Path, packet_id: str) -> dict:
    if not queue_path.exists():
        return {}
    q = pd.read_csv(queue_path, sep="\t", dtype=str).fillna("")
    hit = q[q["packet_id"] == packet_id]
    if hit.empty:
        return {}
    return hit.iloc[0].to_dict()


def compact_rowwise_table(table_path: Path, max_rows: int = 250, max_chars: int = 80000) -> dict:
    if not table_path.exists():
        return {"status": "missing", "path": str(table_path), "text": ""}

    x = pd.read_csv(table_path, sep="\t", dtype=str).fillna("")

    preferred_cols = [
        "source_row_id", "Run", "BioSample", "PMID", "BioProject",
        "LibraryStrategy", "sra_LibraryName", "sra_SampleName",
        "biosample_title", "biosample_attr_isolate", "biosample_attr_strain",
        "biosample_attr_genotype", "biosample_attr_developmental_stage",
        "biosample_attr_dev_stage", "biosample_attr_life_stage",
        "biosample_attr_treatment", "biosample_attr_condition",
        "biosample_attr_target", "biosample_attr_antibody",
        "detected_stage_terms", "detected_strain_terms",
        "detected_control_terms", "detected_perturbation_terms",
        "detected_assay_target_terms",
        "public_metadata_evidence_compact",
    ]
    cols = [c for c in preferred_cols if c in x.columns]
    y = x[cols].head(max_rows).copy()

    text = y.to_csv(sep="\t", index=False)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[TRUNCATED]\n"

    return {
        "status": "ok",
        "path": str(table_path),
        "n_rows_total": len(x),
        "n_rows_in_prompt": len(y),
        "columns": cols,
        "text": text,
    }


def make_prompt(packet: dict, queue_row: dict, rowwise_compact: dict, pdf_texts: dict[str, str]) -> str:
    packet_brief = {
        "packet_version": packet.get("packet_version"),
        "packet_id": packet.get("packet_id"),
        "unit": packet.get("unit"),
        "paper_context": packet.get("paper_context"),
        "sidecar_rowwise_evidence_table": packet.get("sidecar_rowwise_evidence_table"),
        "sample_label_groups": packet.get("sample_label_groups", [])[:80],
    }

    queue_context = {
        k: queue_row.get(k, "")
        for k in [
            "packet_id", "n_rows", "paper_pdf_count",
            "assay_class", "pre_ai_analysis_readiness",
            "main_ai_task", "assay_specific_required_outputs",
            "assay_aware_priority_tier", "assay_aware_recommended_action",
            "assay_aware_curator_priority",
        ]
        if k in queue_row
    }

    pdf_block = ""
    if pdf_texts:
        parts = []
        for path, text in pdf_texts.items():
            parts.append(f"\n\n===== BEGIN PDF TEXT: {path} =====\n{text}\n===== END PDF TEXT =====")
        pdf_block = "\n".join(parts)
    else:
        pdf_block = "[No PDF text available.]"

    return f"""
You are an expert scientific curation assistant for Plasmodium public sequencing data.

Return ONLY valid JSON. No markdown. No prose outside JSON.

The final goal is a trusted rowwise/runwise processing manifest.
You must help human curators by reading the paper and public metadata evidence,
then proposing sample maps, rowwise annotations, analysis readiness, confidence, and evidence pointers.

Strict policies:
- Do not invent facts.
- If evidence is missing or conflicting, say unknown and flag it.
- AI outputs are suggestions only.
- Human curators make final decisions.
- The rowwise evidence table is the source of truth for Run/source_row_id/sample-label mapping.
- Every source_row_id in the rowwise evidence table must appear exactly once in rowwise_suggestions.
- sample_map must be a PARTITION of the rowwise evidence table into mutually exclusive real biological sample classes.
- Every source_row_id in the rowwise evidence table must appear exactly once across all sample_map.matched_source_row_ids.
- Never put the same source_row_id in more than one sample_map entry.
- Do not omit uncertain rows from sample_map. If necessary, create an unknown_or_ambiguous real sample class and flag it.
- Do not create sample_map classes that are only conceptual contrasts, comparison groups, or analytic contexts. sample_map entries must correspond to real row groups.
- A control sample may be used as comparator for multiple contrasts, but it still appears only once in sample_map. Put contrast/comparator reuse in rowwise_suggestions, analysis_readiness, or global_warnings.
- Do not duplicate rows in sample_map to represent perturbation-vs-control, stage comparisons, replicate logic, or multiple downstream analyses.
- Do not override explicit sample labels. If a row says nodrug/no-drug/control/ctrl, do not label it DHA/BTZ/drug-treated.
- If a row says DHA, label treatment as DHA. If it says BTZ/bortezomib, label treatment as BTZ.
- If row evidence and paper interpretation conflict, preserve row evidence and flag the conflict.
- For RNA-seq perturbation/KD/drug studies, identify matched WT/untreated/vehicle/no-drug comparator groups for DEG readiness.
- For RNA-seq expression/time-course studies, expression-only WT data can be useful if stage/strain/sample meaning is clear.
- For ChIP/CUT&RUN/CUT&Tag-like data, target and matched background/control are analysis-critical.
- If ChIP-like samples lack input/IgG/untagged/matched background, mark peak_calling_not_ready or partial.
- Keep evidence pointers short and checkable.

Assay-aware queue context:
{json.dumps(queue_context, indent=2)}

Before returning JSON, internally check these structural invariants:
1. len(rowwise_suggestions) must equal n_rows_total from the rowwise evidence table.
2. The set of rowwise_suggestions.source_row_id must equal the source_row_id column exactly.
3. The union of sample_map.matched_source_row_ids must equal the source_row_id column exactly.
4. No source_row_id may appear more than once across sample_map.matched_source_row_ids.
5. sample_map is for real biological sample classes only; contrasts/comparisons are not sample classes.

Expected output JSON schema:
{json.dumps(OUTPUT_SCHEMA, indent=2)}

Paper packet brief:
{json.dumps(packet_brief, indent=2)}

Compact rowwise evidence table:
status={rowwise_compact.get("status")}
path={rowwise_compact.get("path")}
n_rows_total={rowwise_compact.get("n_rows_total", "")}
n_rows_in_prompt={rowwise_compact.get("n_rows_in_prompt", "")}

===== BEGIN ROWWISE EVIDENCE TSV =====
{rowwise_compact.get("text", "")}
===== END ROWWISE EVIDENCE TSV =====

===== BEGIN PAPER TEXT CONTEXT =====
{pdf_block}
===== END PAPER TEXT CONTEXT =====
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-id", default=None)
    parser.add_argument("--packet-json", default=None)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-pdf-chars", type=int, default=120000)
    parser.add_argument("--max-rowwise-rows", type=int, default=250)
    parser.add_argument("--max-rowwise-chars", type=int, default=80000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(Path(".env"))

    packet_path = choose_packet(args)
    packet = json.loads(packet_path.read_text())
    packet_id = packet.get("packet_id", packet_path.stem)

    queue_row = load_queue_row(args.queue, packet_id)

    sidecar = Path(packet.get("sidecar_rowwise_evidence_table", ""))
    rowwise_compact = compact_rowwise_table(
        sidecar,
        max_rows=args.max_rowwise_rows,
        max_chars=args.max_rowwise_chars,
    )

    pdf_texts = {}
    for pdf in packet.get("paper_context", {}).get("paper_pdf_candidates", []):
        p = Path(pdf)
        if p.exists():
            pdf_texts[str(p)] = extract_pdf_text(p, max_chars=args.max_pdf_chars)

    prompt = make_prompt(packet, queue_row, rowwise_compact, pdf_texts)

    out_base = args.out_dir / packet_id
    out_base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_path = out_base / f"{packet_id}.prompt.{timestamp}.txt"
    raw_path = out_base / f"{packet_id}.raw_response.{timestamp}.txt"
    json_path = out_base / f"{packet_id}.ai_curation.{timestamp}.json"
    audit_path = out_base / f"{packet_id}.audit.{timestamp}.json"

    prompt_path.write_text(prompt)

    if args.dry_run:
        print(f"Dry run. Wrote prompt: {prompt_path}")
        print(f"Prompt chars: {len(prompt)}")
        return

    if os.getenv("AGENTIC_AI_ENABLE_API", "0") != "1":
        raise RuntimeError("API disabled. Set AGENTIC_AI_ENABLE_API=1 in .env or shell.")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set.")

    model = args.model or os.getenv("OPENAI_SMALL_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
    )

    raw = response.output_text
    raw_path.write_text(raw)

    parsed = safe_json_loads(raw)
    json_path.write_text(json.dumps(parsed, indent=2))

    audit = {
        "timestamp": timestamp,
        "model": model,
        "packet_id": packet_id,
        "packet_json": str(packet_path),
        "queue": str(args.queue),
        "sidecar_rowwise_evidence_table": str(sidecar),
        "prompt_path": str(prompt_path),
        "raw_response_path": str(raw_path),
        "json_output_path": str(json_path),
        "audit_path": str(audit_path),
        "pdfs_used": list(pdf_texts.keys()),
        "prompt_chars": len(prompt),
        "rowwise_compact": {k: v for k, v in rowwise_compact.items() if k != "text"},
    }
    audit_path.write_text(json.dumps(audit, indent=2))

    print(f"Wrote AI curation JSON: {json_path}")
    print(f"Wrote raw response:     {raw_path}")
    print(f"Wrote audit:            {audit_path}")


if __name__ == "__main__":
    main()
