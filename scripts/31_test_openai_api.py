#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def main() -> None:
    load_dotenv(Path(".env"))

    model = os.getenv("OPENAI_SMALL_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.5-mini"

    if os.getenv("AGENTIC_AI_ENABLE_API", "0") != "1":
        raise RuntimeError(
            "API usage is disabled by default. Set AGENTIC_AI_ENABLE_API=1 in .env "
            "or your shell only when intentionally testing/running API-assisted curation."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or export it in your shell.")

    client = OpenAI()

    response = client.responses.create(
        model=model,
        input="Reply with exactly: API connection OK",
    )

    print(response.output_text)


if __name__ == "__main__":
    main()
