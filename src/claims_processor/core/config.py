"""Environment + policy_terms.json loaders.

All configuration is function-based and side-effect free except for
`load_env()` which populates os.environ from a .env file on disk.
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_POLICY_PATH = _REPO_ROOT / "PROBLEM_STATEMENT" / "policy_terms.json"


def load_env(env_file: str | Path | None = None) -> None:
    """Load variables from a .env file into os.environ.

    Idempotent — safe to call multiple times. If `env_file` is None, searches
    for a `.env` at the repo root.
    """
    path = Path(env_file) if env_file else _REPO_ROOT / ".env"
    if path.exists():
        load_dotenv(path, override=False)


def get_env(key: str, default: str | None = None, required: bool = False) -> str | None:
    """Read an env var. If `required=True` and missing, raise RuntimeError."""
    value = os.environ.get(key, default)
    if required and not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


@lru_cache(maxsize=4)
def load_policy_terms(path: str | Path | None = None) -> dict[str, Any]:
    """Read policy_terms.json and return the parsed dict.

    Cached by path so repeated calls during a single process do not re-read
    the file. Pass `path=None` to use the default bundled PROBLEM_STATEMENT copy.
    """
    policy_path = Path(path) if path else _DEFAULT_POLICY_PATH
    if not policy_path.exists():
        raise FileNotFoundError(f"policy_terms.json not found at {policy_path}")
    with open(policy_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_document_requirements(
    claim_category: str, policy: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    """Return {'required': [...], 'optional': [...]} for a claim category.

    Claim category is case-insensitive ('consultation' == 'CONSULTATION').
    Raises KeyError if the category is not defined in the policy.
    """
    policy = policy or load_policy_terms()
    requirements = policy.get("document_requirements", {})
    key = claim_category.upper()
    if key not in requirements:
        raise KeyError(
            f"Unknown claim_category '{claim_category}'. "
            f"Valid categories: {sorted(requirements.keys())}"
        )
    entry = requirements[key]
    return {
        "required": list(entry.get("required", [])),
        "optional": list(entry.get("optional", [])),
    }


def list_claim_categories(policy: dict[str, Any] | None = None) -> list[str]:
    """All claim categories defined in the policy."""
    policy = policy or load_policy_terms()
    return sorted(policy.get("document_requirements", {}).keys())
