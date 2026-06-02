# Background/control matching context

Nachi previously wrote a prototype control-assignment script for ChIP-like metadata curation.

This script should not be rerun as part of the current pipeline. It is retained only as design context for the assistant curator.

Useful conceptual points:
- Match candidate controls within BioProject.
- Treat rows with non-missing background_sample as potential controls/backgrounds.
- Treat rows with missing background_sample as query/experimental samples.
- Use hierarchical matching based on biological metadata:
  - Cell_Cycle_Stage
  - Life_Stage
  - Strain
  - replicate/Replicate
  - Target
  - Condition/Condition1
- Preserve original row order.
- Return candidate control Run IDs.

Important limitations:
- The old script directly assigns assigned_control* columns.
- The new system should instead generate candidate background/control tables with match reasons, warnings, ranks, and curator approval fields.
- Assistant/agentic AI should never directly overwrite the master sheet.
- Final approved controls should be merged back only through stable source_row_id and curation_group_id keys.

Future direction:
The old logic should inspire a new background/control candidate generator, not be used as production code.
