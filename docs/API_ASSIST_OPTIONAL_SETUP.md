# Optional API-assisted curator setup

The core SRA/public-data curator pipeline is deterministic and does not require API access.

API-assisted curation is optional and disabled by default. It is intended to help human curators by reading paper context and metadata packets, then suggesting metadata corrections, likely controls/backgrounds, and evidence summaries.

API outputs are suggestions only. They must not directly overwrite the source master workbook or final curator-approved fields.

## Setup

Install optional API dependencies:

    python -m pip install -r requirements-ai.txt

Copy the example environment file:

    cp .env.example .env

Edit `.env` and add your own API key:

    OPENAI_API_KEY=your_key_here
    OPENAI_MODEL=gpt-5.5
    OPENAI_SMALL_MODEL=gpt-5.4-mini
    AGENTIC_AI_ENABLE_API=1

The `.env` file is ignored by Git and should never be committed.

## Test API access

    python legacy_scripts/review_archive/early_agentic_prototypes/31_test_openai_api.py

Expected output:

    API connection OK

## Reproducibility policy

By default, all repository commands should run without API access.

Any script that calls an API must require explicit opt-in via:

    AGENTIC_AI_ENABLE_API=1

or an explicit command-line flag.

API-assisted outputs should be written to:

    outputs/04_AGENTIC_AI_ASSIST/

and should be treated as non-authoritative suggestions for human review.
