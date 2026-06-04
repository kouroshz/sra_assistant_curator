#!/usr/bin/env python3

"""
Build a compact rowwise public-metadata evidence table from cached SRA RunInfo
and BioSample XML files.

This script is deterministic and does NOT call OpenAI.

Inputs:
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv
  data/sra_runinfo_cache/*.csv
  data/biosample_cache/*.xml

Outputs:
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv
  outputs/02_QC_SUMMARIES/rowwise_public_metadata_evidence_summary.tsv
  outputs/02_QC_SUMMARIES/biosample_attribute_counts_full.tsv
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd


DEFAULT_ROWWISE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv")
DEFAULT_SRA_CACHE = Path("data/sra_runinfo_cache")
DEFAULT_BIOSAMPLE_CACHE = Path("data/biosample_cache")
DEFAULT_OUT = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/rowwise_public_metadata_evidence_summary.tsv")
DEFAULT_ATTR_COUNTS = Path("outputs/02_QC_SUMMARIES/biosample_attribute_counts_full.tsv")


SRA_KEEP_COLUMNS = [
    "Run",
    "Experiment",
    "LibraryName",
    "LibraryStrategy",
    "LibrarySelection",
    "LibrarySource",
    "LibraryLayout",
    "Platform",
    "Model",
    "SRAStudy",
    "BioProject",
    "Study_Pubmed_id",
    "Sample",
    "BioSample",
    "TaxID",
    "ScientificName",
    "SampleName",
    "CenterName",
    "ReleaseDate",
    "download_path",
]


BIOSAMPLE_WANTED_ATTRIBUTES = [
    "sample name",
    "Submitter Id",
    "External Id",
    "isolate",
    "strain",
    "clone",
    "genotype",
    "phenotype",
    "disease",
    "sampling site",
    "sample description",
    "developmental stage",
    "dev stage",
    "life stage",
    "time point",
    "timepoint",
    "treatment",
    "condition",
    "antibody",
    "target",
    "cell line",
    "ArrayExpress-DevelopmentalStage",
    "ArrayExpress-Species",
    "ArrayExpress-SPECIES",
]


TERM_PATTERNS = {
    "stage": [
        r"\bring\b", r"\btrophozoite\b", r"\bschizont\b", r"\bgametocyte\b",
        r"\bsporozoite\b", r"\bmerozoite\b", r"\boocyst\b", r"\bliver\b",
        r"\bblood[- ]stage\b", r"\basexual\b", r"\bsexual\b",
        r"\b\d+\s*h(?:r|ours?)?\b", r"\b\d+\s*hpi\b",
    ],
    "strain": [
        r"\b3D7\b", r"\bNF54\b", r"\bDd2\b", r"\bD10\b", r"\bHB3\b",
        r"\b7G8\b", r"\bK1\b", r"\bW2\b", r"\bFCR3\b", r"\bIT\b",
        r"\bANKA\b", r"\b17X\b", r"\bA7A\b",
    ],
    "control": [
        r"\bWT\b", r"\bwild[- ]type\b", r"\bcontrol\b", r"\bvehicle\b",
        r"\buntreated\b", r"\binput\b", r"\bIgG\b", r"\bmock\b",
        r"\bempty vector\b", r"\bvector control\b",
    ],
    "perturbation": [
        r"\bKO\b", r"\bknockout\b", r"\bKD\b", r"\bknockdown\b",
        r"\bglmS\b", r"\bribozyme\b", r"\boverexpression\b", r"\bOE\b",
        r"\bmutant\b", r"\bconditional\b", r"\btransgenic\b",
        r"\bGlcN\b", r"\bglucosamine\b", r"\bartemisinin\b",
    ],
    "assay_target": [
        r"\bChIP\b", r"\bCUT&RUN\b", r"\bCUT&Tag\b", r"\bRNA[- ]seq\b",
        r"\bATAC\b", r"\bIP\b", r"\bantibody\b", r"\bHA\b", r"\bGFP\b",
        r"\bFLAG\b", r"\bmyc\b",
    ],
}


def clean_value(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def compact_join(parts, sep=" | ", max_chars=2000) -> str:
    vals = [clean_value(x) for x in parts if clean_value(x)]
    out = sep.join(vals)
    if len(out) > max_chars:
        return out[:max_chars] + "..."
    return out


def normalize_attr_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


def parse_sra_cache(sra_cache: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(sra_cache.glob("*.csv")):
        try:
            x = pd.read_csv(f, dtype=str)
            if len(x) == 0:
                rows.append({"Run": f.stem, "sra_parse_status": "empty_csv", "sra_cache_path": str(f)})
                continue
            row = x.iloc[0].to_dict()
            row = {k: clean_value(v) for k, v in row.items()}
            row["Run"] = row.get("Run") or f.stem
            row["sra_parse_status"] = "ok"
            row["sra_cache_path"] = str(f)
            rows.append(row)
        except Exception as e:
            rows.append({
                "Run": f.stem,
                "sra_parse_status": f"error:{type(e).__name__}:{e}",
                "sra_cache_path": str(f),
            })

    sra = pd.DataFrame(rows)
    if sra.empty:
        sra = pd.DataFrame(columns=["Run"])

    keep = [c for c in SRA_KEEP_COLUMNS if c in sra.columns]
    extra = [c for c in ["sra_parse_status", "sra_cache_path"] if c in sra.columns]
    sra = sra[keep + extra].copy()

    rename = {c: f"sra_{c}" for c in sra.columns if c != "Run"}
    sra = sra.rename(columns=rename)
    return sra


def parse_biosample_file(path: Path) -> dict:
    rec = {
        "BioSample": path.stem,
        "biosample_cache_path": str(path),
        "biosample_parse_status": "",
    }

    try:
        root = ET.parse(path).getroot()
        bs = root.find(".//BioSample")
        if bs is None:
            rec["biosample_parse_status"] = "no_biosample_record"
            return rec

        rec["biosample_parse_status"] = "ok"
        rec["biosample_uid"] = clean_value(bs.attrib.get("id", ""))
        rec["biosample_accession"] = clean_value(bs.attrib.get("accession", ""))

        rec["biosample_title"] = clean_value(bs.findtext(".//Description/Title"))

        org = bs.find(".//Organism")
        if org is not None:
            rec["biosample_taxonomy_name"] = clean_value(org.attrib.get("taxonomy_name", ""))
            rec["biosample_taxonomy_id"] = clean_value(org.attrib.get("taxonomy_id", ""))
            rec["biosample_organism_name"] = clean_value(org.findtext("OrganismName"))

        comment_texts = []
        for p in bs.findall(".//Comment/Paragraph"):
            txt = clean_value(p.text)
            if txt:
                comment_texts.append(txt)
        rec["biosample_comment_compact"] = compact_join(comment_texts, max_chars=1500)

        attrs = {}
        for a in bs.findall(".//Attributes/Attribute"):
            name = clean_value(a.attrib.get("attribute_name", ""))
            val = clean_value(a.text)
            if name and val:
                attrs[name] = val

        rec["biosample_n_attributes"] = len(attrs)
        rec["biosample_attributes_compact"] = compact_join(
            [f"{k}: {v}" for k, v in sorted(attrs.items())],
            max_chars=2500,
        )

        lower = {k.lower(): v for k, v in attrs.items()}
        for attr in BIOSAMPLE_WANTED_ATTRIBUTES:
            key = "biosample_attr_" + normalize_attr_name(attr)
            rec[key] = lower.get(attr.lower(), "")

    except Exception as e:
        rec["biosample_parse_status"] = f"error:{type(e).__name__}:{e}"

    return rec


def parse_biosample_cache(biosample_cache: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    records = []
    attr_counter = {}

    for f in sorted(biosample_cache.glob("*.xml")):
        rec = parse_biosample_file(f)
        records.append(rec)

        attrs = rec.get("biosample_attributes_compact", "")
        for part in attrs.split(" | "):
            if ": " in part:
                k = part.split(": ", 1)[0]
                attr_counter[k] = attr_counter.get(k, 0) + 1

    bio = pd.DataFrame(records)
    if bio.empty:
        bio = pd.DataFrame(columns=["BioSample"])

    attr_counts = pd.DataFrame(
        [{"attribute": k, "n_biosamples": v} for k, v in sorted(attr_counter.items(), key=lambda x: (-x[1], x[0]))]
    )
    return bio, attr_counts


def detect_terms(text: str, kind: str) -> str:
    hits = []
    for pat in TERM_PATTERNS[kind]:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            val = m.group(0)
            if val not in hits:
                hits.append(val)
    return ";".join(hits[:20])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rowwise", type=Path, default=DEFAULT_ROWWISE)
    parser.add_argument("--sra-cache", type=Path, default=DEFAULT_SRA_CACHE)
    parser.add_argument("--biosample-cache", type=Path, default=DEFAULT_BIOSAMPLE_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--attr-counts", type=Path, default=DEFAULT_ATTR_COUNTS)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.attr_counts.parent.mkdir(parents=True, exist_ok=True)

    rowwise = pd.read_csv(args.rowwise, sep="\t", dtype=str)
    sra = parse_sra_cache(args.sra_cache)
    bio, attr_counts = parse_biosample_cache(args.biosample_cache)

    merged = rowwise.merge(sra, on="Run", how="left")
    merged = merged.merge(bio, on="BioSample", how="left")

    # Build compact evidence text from current master + SRA + BioSample.
    evidence_cols = [
        "Run", "BioSample", "PMID", "BioProject",
        "Title", "LibraryName", "SampleName", "ScientificName",
        "sra_LibraryName", "sra_SampleName", "sra_ScientificName",
        "biosample_title", "biosample_taxonomy_name",
        "biosample_attr_sample_name", "biosample_attr_submitter_id",
        "biosample_attr_isolate", "biosample_attr_strain",
        "biosample_attr_clone", "biosample_attr_genotype",
        "biosample_attr_phenotype", "biosample_attr_disease",
        "biosample_attr_sampling_site",
        "biosample_attr_developmental_stage",
        "biosample_attr_dev_stage",
        "biosample_attr_life_stage",
        "biosample_attr_time_point",
        "biosample_attr_timepoint",
        "biosample_attr_treatment",
        "biosample_attr_condition",
        "biosample_attr_antibody",
        "biosample_attr_target",
        "biosample_attr_arrayexpress_developmentalstage",
        "biosample_comment_compact",
        "biosample_attributes_compact",
    ]
    evidence_cols = [c for c in evidence_cols if c in merged.columns]

    def make_evidence(row):
        parts = []
        for c in evidence_cols:
            v = clean_value(row.get(c, ""))
            if v:
                parts.append(f"{c}={v}")
        return compact_join(parts, max_chars=4000)

    merged["public_metadata_evidence_compact"] = merged.apply(make_evidence, axis=1)

    for kind in TERM_PATTERNS:
        merged[f"detected_{kind}_terms"] = merged["public_metadata_evidence_compact"].map(
            lambda x, k=kind: detect_terms(x, k)
        )

    # Simple flags for AI triage.
    def has_any(row, cols):
        return any(clean_value(row.get(c, "")) for c in cols if c in row.index)

    stage_cols = [
        "Cell_Cycle_Stage", "Life_Stage",
        "biosample_attr_developmental_stage", "biosample_attr_dev_stage",
        "biosample_attr_life_stage", "biosample_attr_arrayexpress_developmentalstage",
    ]
    strain_cols = ["Strain", "sra_ScientificName", "biosample_attr_isolate", "biosample_attr_strain"]
    condition_cols = [
        "Condition1", "Condition2", "Condition3",
        "Mutant", "biosample_attr_genotype", "biosample_attr_treatment",
        "biosample_attr_condition",
    ]

    merged["has_stage_evidence"] = merged.apply(lambda r: has_any(r, stage_cols) or bool(clean_value(r.get("detected_stage_terms", ""))), axis=1)
    merged["has_strain_evidence"] = merged.apply(lambda r: has_any(r, strain_cols) or bool(clean_value(r.get("detected_strain_terms", ""))), axis=1)
    merged["has_condition_evidence"] = merged.apply(lambda r: has_any(r, condition_cols) or bool(clean_value(r.get("detected_perturbation_terms", ""))), axis=1)

    merged["needs_ai"] = merged.apply(
        lambda r: not (r["has_stage_evidence"] and r["has_strain_evidence"] and r["has_condition_evidence"]),
        axis=1,
    )

    # Keep a useful column order without dropping the original data.
    front = [
        "source_row_id", "source_row_number", "curation_group_id", "Run", "BioSample",
        "PMID", "BioProject", "LibraryStrategy",
        "LibraryName", "SampleName", "ScientificName",
        "sra_LibraryName", "sra_SampleName", "sra_ScientificName",
        "biosample_title", "biosample_taxonomy_name",
        "biosample_attr_sample_name", "biosample_attr_submitter_id",
        "biosample_attr_isolate", "biosample_attr_strain",
        "biosample_attr_genotype", "biosample_attr_phenotype",
        "biosample_attr_disease", "biosample_attr_sampling_site",
        "biosample_attr_developmental_stage", "biosample_attr_dev_stage",
        "biosample_attr_life_stage", "biosample_attr_treatment",
        "biosample_attr_condition",
        "biosample_attr_arrayexpress_developmentalstage",
        "detected_stage_terms", "detected_strain_terms",
        "detected_control_terms", "detected_perturbation_terms",
        "detected_assay_target_terms",
        "has_stage_evidence", "has_strain_evidence", "has_condition_evidence",
        "needs_ai",
        "public_metadata_evidence_compact",
    ]
    front = [c for c in front if c in merged.columns]
    rest = [c for c in merged.columns if c not in front]
    out = merged[front + rest]

    out.to_csv(args.out, sep="\t", index=False)
    attr_counts.to_csv(args.attr_counts, sep="\t", index=False)

    summary = []
    summary.append({"metric": "n_rowwise_rows", "value": len(out)})
    summary.append({"metric": "n_sra_cache_files", "value": len(list(args.sra_cache.glob('*.csv')))})
    summary.append({"metric": "n_biosample_cache_files", "value": len(list(args.biosample_cache.glob('*.xml')))})
    sra_status_col = "sra_sra_parse_status" if "sra_sra_parse_status" in out.columns else "sra_parse_status"
    bio_status_col = "biosample_parse_status"

    summary.append({"metric": "n_rows_with_sra_cache", "value": int(out.get(sra_status_col, pd.Series(dtype=str)).eq("ok").sum())})
    summary.append({"metric": "n_rows_with_biosample_cache", "value": int(out.get(bio_status_col, pd.Series(dtype=str)).eq("ok").sum())})

    for c in [
        "sra_LibraryName", "sra_SampleName", "sra_ScientificName",
        "biosample_title", "biosample_attr_isolate", "biosample_attr_strain",
        "biosample_attr_genotype", "biosample_attr_developmental_stage",
        "biosample_attr_dev_stage", "biosample_attr_arrayexpress_developmentalstage",
        "detected_stage_terms", "detected_strain_terms",
        "detected_perturbation_terms",
        "detected_control_terms",
    ]:
        if c in out.columns:
            summary.append({"metric": f"nonempty_{c}", "value": int(out[c].map(clean_value).astype(bool).sum())})

    for c in ["has_stage_evidence", "has_strain_evidence", "has_condition_evidence", "needs_ai"]:
        if c in out.columns:
            summary.append({"metric": f"true_{c}", "value": int(out[c].astype(bool).sum())})

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote evidence table: {args.out}")
    print(f"Wrote summary:        {args.summary}")
    print(f"Wrote attr counts:    {args.attr_counts}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
