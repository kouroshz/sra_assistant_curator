# ChIP AI-curation Phase Completion Report

Generated: 2026-06-03T21:13:09

## Executive status

- ChIP packets inspected: 42
- Active validated PASS packets: 42
- Repaired active outputs: 11
- Rowwise review rows: 733
- Target-control map rows: 490

## Output status counts

- active_validated_pass: 42

## ChIP peak-calling readiness

- yes: 30
- partial: 11
- no: 1

## Interpretation

- All ChIP AI outputs are structurally validated.
- AI outputs remain suggestions only; curator final fields are authoritative.
- `partial` or `no` peak-calling readiness should remain visible to curators.
- Shared input/control reuse is expected in ChIP and should be reviewed through the target-control map.

## Files written

- `outputs/06_CHIP_AI_ASSIST/20_final_qc/trusted_chip_ai_phase_packet_status.tsv`
- `outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv`
- `outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv`