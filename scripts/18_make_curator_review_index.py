#!/usr/bin/env python3

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATA = ROOT / "data"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    return x


def counts_string(s):
    vc = s.fillna("").astype(str).replace("", "blank").value_counts()
    return "; ".join([f"{k}:{v}" for k, v in vc.items()])


def read_special():
    f = DATA / "special_pmid_handling.tsv"
    if not f.exists():
        return {}
    df = pd.read_csv(f, sep="\t", dtype=str).fillna("")
    return {clean(r["PMID"]): r.to_dict() for _, r in df.iterrows()}


def main():
    status_file = OUT / "batch_curator_pipeline_status.tsv"
    candidates_file = OUT / "pmid_candidates.tsv"

    status = pd.read_csv(status_file, sep="\t", dtype=str).fillna("")
    candidates = pd.read_csv(candidates_file, sep="\t", dtype=str).fillna("")
    special = read_special()

    candidate_lookup = {clean(r["PMID"]): r.to_dict() for _, r in candidates.iterrows()}

    rows = []

    for _, srow in status.iterrows():
        pmid = clean(srow["PMID"])
        cand = candidate_lookup.get(pmid, {})
        sp = special.get(pmid, {})

        row_file = OUT / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv"
        ordinary_review = OUT / f"PMID_{pmid}_curator_review_view.xlsx"
        collapsed_review = OUT / f"PMID_{pmid}_single_cell_collapsed_review.xlsx"

        if collapsed_review.exists():
            primary_review = collapsed_review
            review_mode = "collapsed_special"
            curator_action = "Review collapsed workbook only; do not manually curate SRR-level rows."
        else:
            primary_review = ordinary_review
            review_mode = "row_level"
            curator_action = "Review row-level workbook."

        if row_file.exists():
            df = pd.read_csv(row_file, sep="\t", dtype=str).fillna("")
            n_rows = len(df)
            needs_yes = int((df.get("needs_human_review", "") == "yes").sum()) if "needs_human_review" in df else ""
            needs_no = int((df.get("needs_human_review", "") == "no").sum()) if "needs_human_review" in df else ""
            conf_high = int((df.get("curation_confidence", "") == "high").sum()) if "curation_confidence" in df else ""
            conf_medium = int((df.get("curation_confidence", "") == "medium").sum()) if "curation_confidence" in df else ""
            conf_low = int((df.get("curation_confidence", "") == "low").sum()) if "curation_confidence" in df else ""
            factor_counts = counts_string(df["experimental_factor"]) if "experimental_factor" in df else ""
            role_counts = counts_string(df["control_role"]) if "control_role" in df else ""
        else:
            n_rows = needs_yes = needs_no = conf_high = conf_medium = conf_low = ""
            factor_counts = role_counts = ""

        rows.append({
            "PMID": pmid,
            "Title": cand.get("local_pdf", "").replace(f"{pmid}_", "").replace(".pdf", "").replace("_", " "),
            "n_master_rows": cand.get("n_rows", ""),
            "n_output_rows": n_rows,
            "BioProjects": cand.get("BioProjects", ""),
            "LibraryStrategies": cand.get("LibraryStrategies", ""),
            "pipeline_status": srow.get("status", ""),
            "review_mode": review_mode,
            "primary_review_file": str(primary_review),
            "ordinary_row_level_file": str(ordinary_review),
            "row_level_data_file": str(row_file),
            "curator_action": curator_action,
            "special_handling": sp.get("special_handling", ""),
            "curation_scope": sp.get("curation_scope", ""),
            "review_unit": sp.get("review_unit", ""),
            "row_level_curation_recommended": sp.get("row_level_curation_recommended", ""),
            "needs_review_yes": needs_yes,
            "needs_review_no": needs_no,
            "confidence_high": conf_high,
            "confidence_medium": conf_medium,
            "confidence_low": conf_low,
            "experimental_factor_counts": factor_counts,
            "control_role_counts": role_counts,
        })

    index = pd.DataFrame(rows)

    # Priority ranking: special first, then many review rows, then unknown-heavy.
    index["needs_review_yes_num"] = pd.to_numeric(index["needs_review_yes"], errors="coerce").fillna(0).astype(int)
    index["n_output_rows_num"] = pd.to_numeric(index["n_output_rows"], errors="coerce").fillna(0).astype(int)

    index = index.sort_values(
        ["review_mode", "needs_review_yes_num", "n_output_rows_num"],
        ascending=[True, False, False],
    )

    overview = pd.DataFrame([
        {
            "n_pmids": index.shape[0],
            "n_ok": int((index["pipeline_status"] == "ok").sum()),
            "n_special_collapsed": int((index["review_mode"] == "collapsed_special").sum()),
            "n_row_level": int((index["review_mode"] == "row_level").sum()),
            "total_output_rows": int(index["n_output_rows_num"].sum()),
            "total_needs_review_yes": int(index["needs_review_yes_num"].sum()),
        }
    ])

    special_df = index[index["review_mode"] == "collapsed_special"].copy()
    high_review = index.sort_values("needs_review_yes_num", ascending=False).head(20).copy()

    out_xlsx = OUT / "curator_review_index.xlsx"
    out_tsv = OUT / "curator_review_index.tsv"

    index.drop(columns=["needs_review_yes_num", "n_output_rows_num"]).to_csv(out_tsv, sep="\t", index=False)

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="Overview", index=False)
        index.drop(columns=["needs_review_yes_num", "n_output_rows_num"]).to_excel(writer, sheet_name="Review_Index", index=False)
        special_df.drop(columns=["needs_review_yes_num", "n_output_rows_num"]).to_excel(writer, sheet_name="Special_Handling", index=False)
        high_review.drop(columns=["needs_review_yes_num", "n_output_rows_num"]).to_excel(writer, sheet_name="High_Review_Load", index=False)

    print("\n=== Curator review index written ===")
    print(out_xlsx)
    print(out_tsv)
    print("\nOverview:")
    print(overview.to_string(index=False))

    print("\nSpecial handling:")
    if special_df.empty:
        print("None")
    else:
        print(special_df[["PMID", "review_mode", "primary_review_file", "curator_action"]].to_string(index=False))


if __name__ == "__main__":
    main()
