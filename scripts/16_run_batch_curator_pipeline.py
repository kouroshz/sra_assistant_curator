#!/usr/bin/env python3

from pathlib import Path
import argparse
import subprocess
import sys
import time
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
LOGS = OUT / "batch_logs"
LOGS.mkdir(parents=True, exist_ok=True)


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    return x


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--candidates", default=str(OUT / "pmid_candidates.tsv"))
    parser.add_argument("--pmids", default="", help="Comma-separated PMID list. If blank, use all candidates.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sort", choices=["rows_asc", "rows_desc", "as_is"], default="rows_asc")
    parser.add_argument("--with-paper", action="store_true")
    parser.add_argument("--make-review", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--sleep-between", type=float, default=0.0)
    args = parser.parse_args()

    cand = pd.read_csv(args.candidates, sep="\t", dtype=str).fillna("")
    cand["n_rows_num"] = pd.to_numeric(cand["n_rows"], errors="coerce").fillna(0).astype(int)

    if args.pmids.strip():
        wanted = {clean(x) for x in args.pmids.split(",") if clean(x)}
        cand = cand[cand["PMID"].map(clean).isin(wanted)].copy()

    if args.sort == "rows_asc":
        cand = cand.sort_values("n_rows_num", ascending=True)
    elif args.sort == "rows_desc":
        cand = cand.sort_values("n_rows_num", ascending=False)

    if args.limit and args.limit > 0:
        cand = cand.head(args.limit)

    rows = []

    for i, row in enumerate(cand.to_dict("records"), start=1):
        pmid = clean(row["PMID"])
        n_rows = clean(row.get("n_rows", ""))

        review_file = OUT / f"PMID_{pmid}_curator_review_view.xlsx"
        if args.skip_existing and review_file.exists():
            print(f"[{i}/{len(cand)}] PMID {pmid}: skip existing")
            rows.append({
                "PMID": pmid,
                "n_rows": n_rows,
                "status": "skipped_existing",
                "returncode": 0,
                "log_file": "",
                "review_file": str(review_file),
            })
            continue

        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_curator_pipeline.py"),
            "--pmid", pmid,
            "--email", args.email,
        ]

        if args.with_paper:
            cmd.append("--with-paper")
        if args.make_review:
            cmd.append("--make-review")

        log_file = LOGS / f"PMID_{pmid}.log"

        print(f"\n[{i}/{len(cand)}] Running PMID {pmid} ({n_rows} rows)")
        print(" ".join(cmd))

        with open(log_file, "w") as log:
            p = subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

        status = "ok" if p.returncode == 0 else "error"
        print(f"PMID {pmid}: {status}, log={log_file}")

        rows.append({
            "PMID": pmid,
            "n_rows": n_rows,
            "status": status,
            "returncode": p.returncode,
            "log_file": str(log_file),
            "review_file": str(review_file) if review_file.exists() else "",
        })

        pd.DataFrame(rows).to_csv(OUT / "batch_curator_pipeline_status.tsv", sep="\t", index=False)

        if args.sleep_between:
            time.sleep(args.sleep_between)

    print("\n=== Batch complete ===")
    status_df = pd.DataFrame(rows)
    print(status_df["status"].value_counts(dropna=False).to_string())
    print(f"Wrote: {OUT / 'batch_curator_pipeline_status.tsv'}")


if __name__ == "__main__":
    main()
