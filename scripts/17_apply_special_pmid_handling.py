#!/usr/bin/env python3

from pathlib import Path
import argparse
import gzip
import re
import urllib.request
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATA = ROOT / "data"
GEO_CACHE = DATA / "geo_cache"
GEO_CACHE.mkdir(exist_ok=True)


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def read_special_table():
    f = DATA / "special_pmid_handling.tsv"
    if not f.exists():
        return pd.DataFrame()
    return pd.read_csv(f, sep="\t", dtype=str).fillna("")


def get_special_row(pmid):
    tab = read_special_table()
    if tab.empty:
        return None
    hit = tab[tab["PMID"].map(clean) == clean(pmid)]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def download_geo_soft(gse):
    out = GEO_CACHE / f"{gse}_family.soft"
    if out.exists() and out.stat().st_size > 0:
        return out

    # GEO FTP path pattern: GSE96nnn for GSE96066.
    prefix = re.sub(r"\d{3}$", "nnn", gse)
    url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{prefix}/{gse}/soft/{gse}_family.soft.gz"

    print(f"Downloading GEO SOFT: {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "sra_paper_curator/0.1 academic curation"},
    )

    with urllib.request.urlopen(req, timeout=90) as r:
        gz_bytes = r.read()

    text = gzip.decompress(gz_bytes).decode("utf-8", errors="replace")
    out.write_text(text)
    return out


def parse_geo_soft(gse):
    f = download_geo_soft(gse)
    records = []
    cur = None

    def save():
        if cur:
            records.append(cur.copy())

    for line in f.read_text(errors="replace").splitlines():
        line = line.rstrip("\n")

        if line.startswith("^SAMPLE = "):
            save()
            cur = {"geo_accession": line.split("=", 1)[1].strip()}
            continue

        if cur is None:
            continue

        if line.startswith("!Sample_title = "):
            cur["geo_title"] = line.split("=", 1)[1].strip()

        elif line.startswith("!Sample_source_name_ch1 = "):
            cur["geo_source_name"] = line.split("=", 1)[1].strip()

        elif line.startswith("!Sample_organism_ch1 = "):
            cur["geo_organism"] = line.split("=", 1)[1].strip()

        elif line.startswith("!Sample_characteristics_ch1 = "):
            val = line.split("=", 1)[1].strip()
            if ":" in val:
                k, v = val.split(":", 1)
                k = "geo_" + re.sub(r"[^A-Za-z0-9]+", "_", k.strip().lower()).strip("_")
                cur[k] = v.strip()

        elif line.startswith("!Sample_relation = "):
            val = line.split("=", 1)[1].strip()

            m = re.search(r"(SRX\d+)", val)
            if m:
                cur["Experiment"] = m.group(1)

            m = re.search(r"(SAMN\d+)", val)
            if m:
                cur["BioSample"] = m.group(1)

    save()

    geo = pd.DataFrame(records).fillna("")
    return geo


def infer_well(title):
    title = clean(title)
    m = re.search(r"(\d+hpi)_([A-P])(\d{1,2})$", title)
    if not m:
        return "", "", "", ""
    return m.group(1), f"{m.group(2)}{m.group(3)}", m.group(2), m.group(3)


def condition_from_induced(induced):
    v = clean(induced).lower()

    if v == "induced":
        return "-SerM / LysoPC depletion / gametocyte induction", "experimental"

    if v in {"not induced", "non-induced", "uninduced", "control"}:
        return "-SerM + LysoPC control / no induction", "control"

    if v in {"n/a", "na", "unknown"}:
        return "unknown induction status / technical unknown barcode", "unknown"

    return "", "unknown"


def annotate_rows(df, pmid, special):
    df = df.copy().fillna("")

    for c in [
        "special_handling",
        "curation_scope",
        "curator_review_unit",
        "row_level_curation_recommended",
        "special_handling_note",
        "geo_accession",
        "geo_title",
        "geo_time_point",
        "geo_induced",
        "geo_condition",
        "geo_well",
        "geo_plate_row",
        "geo_plate_column",
    ]:
        if c not in df.columns:
            df[c] = ""

    # Currently only 30320226 uses GEO GSE96066 metadata.
    if clean(pmid) == "30320226":
        geo = parse_geo_soft("GSE96066")
        geo_lookup = {
            clean(r.get("Experiment", "")): r
            for _, r in geo.iterrows()
            if clean(r.get("Experiment", ""))
        }
    else:
        geo_lookup = {}

    for idx, row in df.iterrows():
        exp = clean(row.get("Experiment", ""))
        g = geo_lookup.get(exp, {})

        title = clean(g.get("geo_title", ""))
        time_from_title, well, plate_row, plate_col = infer_well(title)

        time_point = clean(g.get("geo_time_point", "")) or time_from_title
        induced = clean(g.get("geo_induced", ""))
        condition, control_role = condition_from_induced(induced)

        is_unknown_barcode = (
            title.lower().endswith("_unknown")
            or induced.lower() in {"n/a", "na", "unknown"}
            or "_unknown" in title.lower()
        )

        df.at[idx, "special_handling"] = clean(special.get("special_handling", ""))
        df.at[idx, "curation_scope"] = clean(special.get("curation_scope", ""))
        df.at[idx, "curator_review_unit"] = clean(special.get("review_unit", ""))
        df.at[idx, "row_level_curation_recommended"] = clean(special.get("row_level_curation_recommended", "no"))
        df.at[idx, "special_handling_note"] = clean(special.get("special_handling_note", ""))

        df.at[idx, "geo_accession"] = clean(g.get("geo_accession", ""))
        df.at[idx, "geo_title"] = title
        df.at[idx, "geo_time_point"] = time_point
        df.at[idx, "geo_induced"] = induced
        df.at[idx, "geo_condition"] = condition
        df.at[idx, "geo_well"] = well
        df.at[idx, "geo_plate_row"] = plate_row
        df.at[idx, "geo_plate_column"] = plate_col

        df.at[idx, "sra_row_omics"] = clean(special.get("sra_row_omics_override", "")) or clean(row.get("sra_row_omics", ""))
        df.at[idx, "experimental_factor"] = clean(special.get("experimental_factor_override", "")) or clean(row.get("experimental_factor", ""))

        if condition:
            df.at[idx, "Condition1"] = condition
        if time_point:
            df.at[idx, "Condition2"] = time_point

        if is_unknown_barcode:
            # Preserve explicit N/A/unknown labels for curator-facing output.
            if not induced:
                induced = "not_applicable_unknown_barcode"
            condition = "unknown induction status / technical unknown barcode"

            df.at[idx, "geo_induced"] = induced
            df.at[idx, "geo_condition"] = condition
            df.at[idx, "Condition1"] = condition
            df.at[idx, "Condition3"] = "technical unknown barcode / not a curated biological well"
            df.at[idx, "control_role"] = "unknown"
            df.at[idx, "curator_condition_note"] = (
                f"Single-cell SCRB-seq technical unknown-barcode record; {time_point}, induced=not_applicable_unknown_barcode. "
                "Keep for traceability but exclude from induced/control biological condition summaries."
            )
            df.at[idx, "review_priority"] = "high"
            df.at[idx, "review_reason"] = (
                "GEO sample title/description indicates unknown barcode and induced=N/A; "
                "not a standard induced/control single-cell well."
            )
        else:
            if well:
                df.at[idx, "Condition3"] = f"single-cell well {well}"

            df.at[idx, "control_role"] = control_role

            if condition and time_point:
                df.at[idx, "curator_condition_note"] = (
                    f"Single-cell DGE well-level archive record; {time_point}, {condition}. "
                    "Review at collapsed timepoint/condition level, not SRR row level."
                )
            else:
                df.at[idx, "curator_condition_note"] = (
                    "Single-cell DGE well-level archive record; review at collapsed dataset/timepoint level."
                )

            df.at[idx, "review_priority"] = "medium"
            df.at[idx, "review_reason"] = (
                "Special single-cell archive representation: SRR rows are technical/cell-level records, "
                "not independent biological samples."
            )

        df.at[idx, "needs_human_review"] = "yes"

    return df


def uniq_join(vals, n=6):
    vals = [clean(v) for v in vals if clean(v)]
    vals = sorted(set(vals))
    if len(vals) > n:
        return ";".join(vals[:n]) + f";...(+{len(vals)-n})"
    return ";".join(vals)


def make_collapsed_workbook(df, pmid, special):
    out_xlsx = OUT / f"PMID_{pmid}_single_cell_collapsed_review.xlsx"

    if "geo_accession" not in df.columns:
        raise RuntimeError("Rows have not been GEO-annotated.")

    by_gsm = (
        df.groupby(
            [
                "geo_accession",
                "geo_title",
                "geo_time_point",
                "geo_induced",
                "geo_condition",
                "geo_well",
                "geo_plate_row",
                "geo_plate_column",
            ],
            dropna=False,
        )
        .agg(
            n_srr_runs=("Run", "nunique"),
            runs=("Run", lambda x: uniq_join(x, n=4)),
            experiment=("Experiment", lambda x: uniq_join(x, n=3)),
            biosample=("BioSample", lambda x: uniq_join(x, n=3)),
            spots_total=("spots", lambda x: pd.to_numeric(x, errors="coerce").sum()),
            bases_total=("bases", lambda x: pd.to_numeric(x, errors="coerce").sum()),
        )
        .reset_index()
    )

    biological_df = df[~df["geo_induced"].map(clean).str.lower().isin({"n/a", "na", "unknown", ""})].copy()
    technical_unknown_df = df[df["geo_induced"].map(clean).str.lower().isin({"n/a", "na", "unknown", ""})].copy()

    by_group = (
        biological_df.groupby(
            ["geo_time_point", "geo_induced", "geo_condition"],
            dropna=False,
        )
        .agg(
            n_geo_samples=("geo_accession", "nunique"),
            n_srr_runs=("Run", "nunique"),
            n_biosamples=("BioSample", "nunique"),
            n_experiments=("Experiment", "nunique"),
            example_geo_samples=("geo_accession", lambda x: uniq_join(x, n=5)),
            example_runs=("Run", lambda x: uniq_join(x, n=5)),
            spots_total=("spots", lambda x: pd.to_numeric(x, errors="coerce").sum()),
            bases_total=("bases", lambda x: pd.to_numeric(x, errors="coerce").sum()),
        )
        .reset_index()
        .sort_values(["geo_time_point", "geo_induced"])
    )

    unknown_group = (
        technical_unknown_df.groupby(
            ["geo_time_point", "geo_induced", "geo_condition"],
            dropna=False,
        )
        .agg(
            n_geo_samples=("geo_accession", "nunique"),
            n_srr_runs=("Run", "nunique"),
            n_biosamples=("BioSample", "nunique"),
            n_experiments=("Experiment", "nunique"),
            example_geo_samples=("geo_accession", lambda x: uniq_join(x, n=10)),
            example_runs=("Run", lambda x: uniq_join(x, n=10)),
            spots_total=("spots", lambda x: pd.to_numeric(x, errors="coerce").sum()),
            bases_total=("bases", lambda x: pd.to_numeric(x, errors="coerce").sum()),
        )
        .reset_index()
        .sort_values(["geo_time_point", "geo_induced"])
    )

    summary = pd.DataFrame(
        [
            {
                "PMID": pmid,
                "Title": clean(df["Title"].iloc[0]) if "Title" in df.columns and len(df) else "",
                "BioProject": uniq_join(df["BioProject"]) if "BioProject" in df.columns else "",
                "GEO_series": "GSE96066",
                "n_srr_rows": len(df),
                "n_srr_runs": df["Run"].nunique() if "Run" in df.columns else "",
                "n_geo_samples": df["geo_accession"].nunique(),
                "n_biosamples": df["BioSample"].nunique() if "BioSample" in df.columns else "",
                "curation_scope": clean(special.get("curation_scope", "")),
                "review_unit": clean(special.get("review_unit", "")),
                "row_level_curation_recommended": clean(special.get("row_level_curation_recommended", "")),
                "sra_row_omics": clean(special.get("sra_row_omics_override", "")),
                "experimental_factor": clean(special.get("experimental_factor_override", "")),
                "curator_note": clean(special.get("special_handling_note", "")),
            }
        ]
    )

    notes = pd.DataFrame(
        [
            {
                "note_type": "interpretation",
                "note": (
                    "This is a single-cell/well-level SRA archive. The SRR rows should be retained for traceability, "
                    "but curator review should happen at the collapsed GEO sample or timepoint/condition level."
                ),
            },
            {
                "note_type": "expected_design",
                "note": (
                    "GEO describes 1152 wells: 1008 induced and 144 non-induced controls across 3 timepoints. "
                    "The paper reports 336 individual cells plus 48 controls per timepoint."
                ),
            },
            {
                "note_type": "processed_data",
                "note": (
                    "Processed matrices on GEO are likely the most useful downstream objects: 38/42/46 hpi raw, "
                    "filtered, normalized matrices plus all.normalized.tsv."
                ),
            },
            {
                "note_type": "technical_unknown_samples",
                "note": (
                    "GEO includes three *_unknown samples with induced=N/A, one per timepoint. "
                    "These should be kept for traceability but excluded from biological induced/control summaries unless a curator confirms otherwise."
                ),
            },
        ]
    )

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Dataset_Summary", index=False)
        by_group.to_excel(writer, sheet_name="Timepoint_Condition", index=False)
        unknown_group.to_excel(writer, sheet_name="Technical_Unknown", index=False)
        by_gsm.to_excel(writer, sheet_name="GEO_Sample_Level", index=False)
        notes.to_excel(writer, sheet_name="Curator_Notes", index=False)

    return out_xlsx, by_group, by_gsm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid", required=True)
    args = ap.parse_args()

    pmid = clean(args.pmid)
    special = get_special_row(pmid)

    if special is None:
        print(f"No special handling rule for PMID {pmid}; no-op.")
        return

    row_files = sorted(OUT.glob(f"PMID_{pmid}_agent_filled_master_rows*.tsv"))
    if not row_files:
        raise FileNotFoundError(f"No agent-filled row files found for PMID {pmid}")

    preferred = None

    for f in row_files:
        df = pd.read_csv(f, sep="\t", dtype=str).fillna("")
        df2 = annotate_rows(df, pmid, special)
        df2.to_csv(f, sep="\t", index=False)
        print(f"Updated: {f}")

        if "with_paper_context" in f.name:
            preferred = df2

    if preferred is None:
        preferred = df2

    out_xlsx, by_group, by_gsm = make_collapsed_workbook(preferred, pmid, special)

    print(f"\n=== Special handling applied for PMID {pmid} ===")
    print(f"Wrote collapsed review workbook: {out_xlsx}")
    print("\nCollapsed timepoint/condition summary:")
    print(by_group.to_string(index=False))
    print(f"\nGEO sample-level rows: {len(by_gsm)}")


if __name__ == "__main__":
    main()
