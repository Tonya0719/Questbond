"""Developer-only OpenRouter key/credit check.

Run with:
    python scripts/check_llm_credit.py

This script does not participate in the agent runtime and does not modify the
SQLite database.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.llm.openrouter_utils import (
    OpenRouterCreditError,
    check_openrouter_credit,
    format_openrouter_credit,
)


def main() -> int:
    base_url = settings.local_llm_base_url.lower()
    if "openrouter.ai" not in base_url:
        print(
            "LOCAL_LLM_BASE_URL is not configured for OpenRouter. "
            "Set it to https://openrouter.ai/api/v1 before using this script."
        )
        return 1

    try:
        data = check_openrouter_credit(
            settings.local_llm_api_key,
            timeout_sec=min(settings.local_llm_timeout_sec, 20),
        )
    except OpenRouterCreditError as exc:
        print(f"could not check OpenRouter credit: {exc}")
        return 1

    print(format_openrouter_credit(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
