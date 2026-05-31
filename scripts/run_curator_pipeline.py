#!/usr/bin/env python3

from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(cmd, label):
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--email", default="")
    parser.add_argument("--sleep", default="2.0")
    parser.add_argument("--with-paper", action="store_true")
    parser.add_argument("--make-review", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    pmid = args.pmid

    steps = [
        ([py, str(SCRIPTS / "01_filter_master_by_pmid.py"), "--pmid", pmid],
         "01 filter master by PMID"),

        ([py, str(SCRIPTS / "02_fetch_sra_runinfo_for_master_rows.py"), "--pmid", pmid],
         "02 fetch SRA RunInfo for existing master rows"),

        ([py, str(SCRIPTS / "03_fetch_biosample_metadata_for_master_rows.py"),
          "--pmid", pmid, "--email", args.email, "--sleep", args.sleep],
         "03 fetch BioSample metadata for existing master rows"),

        ([py, str(SCRIPTS / "04_populate_master_from_biosample.py"),
          "--pmid", pmid, "--assign-controls"],
         "04 populate master copy from BioSample metadata"),
    ]

    if args.with_paper:
        steps.extend([
            ([py, str(SCRIPTS / "07_extract_paper_context.py"), "--pmid", pmid],
             "07 extract paper context"),

            ([py, str(SCRIPTS / "08_apply_paper_context_to_master.py"), "--pmid", pmid],
             "08 apply paper context to master"),
        ])

    # Add derived control/sample grouping columns before curator review.
    steps.append(
        ([py, str(SCRIPTS / "13_add_control_group_columns.py"), "--pmid", pmid],
         "13 add control/sample grouping columns")
    )

    steps.append(
        ([py, str(SCRIPTS / "14_add_curator_condition_fields.py"), "--pmid", pmid],
         "14 add curator-facing condition fields")
    )

    # Optional special handling, e.g. single-cell/cell-level SRA archives.
    steps.append(
        ([py, str(SCRIPTS / "17_apply_special_pmid_handling.py"), "--pmid", pmid],
         "17 apply special PMID handling if configured")
    )

    steps.append(
        ([py, str(SCRIPTS / "21_patch_pmid_31737630_dis3.py"), "--pmid", pmid],
         "21 apply PMID-specific Dis3 patch if configured")
    )

    steps.append(
        ([py, str(SCRIPTS / "22_patch_pmid_34365503_timepoints.py"), "--pmid", pmid],
         "22 apply PMID-specific developmental timepoint patch if configured")
    )

    steps.append(
        ([py, str(SCRIPTS / "23_patch_pmid_32552779_arp4_glcn.py"), "--pmid", pmid],
         "23 apply PMID-specific PfArp4/GlcN patch if configured")
    )

    if args.make_review:
        steps.append(
            ([py, str(SCRIPTS / "09_make_curator_review_view.py"), "--pmid", pmid],
             "09 make curator review view")
        )

    for cmd, label in steps:
        run(cmd, label)

    print("\n" + "=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)

    if args.with_paper:
        final_master = ROOT / "outputs" / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.with_paper_context.xlsx"
        final_rows = ROOT / "outputs" / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv"
    else:
        final_master = ROOT / "outputs" / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.xlsx"
        final_rows = ROOT / "outputs" / f"PMID_{pmid}_agent_filled_master_rows.tsv"

    print(f"Filled master: {final_master}")
    print(f"Filled rows:   {final_rows}")

    review = ROOT / "outputs" / f"PMID_{pmid}_curator_review_view.xlsx"
    if review.exists():
        print(f"Review view:   {review}")


if __name__ == "__main__":
    main()
