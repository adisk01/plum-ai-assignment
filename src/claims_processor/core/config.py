"""Environment + policy_terms.json loaders."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = REPO_ROOT / "PROBLEM_STATEMENT" / "policy_terms.json"


def load_env():
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def get_env(key, default=None):
    return os.environ.get(key, default)


def load_policy_terms(path=None):
    with open(path or POLICY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_document_requirements(claim_category, policy=None):
    policy = policy or load_policy_terms()
    entry = policy["document_requirements"][claim_category.upper()]
    return {
        "required": list(entry.get("required", [])),
        "optional": list(entry.get("optional", [])),
    }


def list_claim_categories(policy=None):
    policy = policy or load_policy_terms()
    return sorted(policy["document_requirements"].keys())


def get_member(member_id, policy=None):
    if not member_id:
        return None
    policy = policy or load_policy_terms()
    for m in policy.get("members", []):
        if m.get("member_id") == member_id:
            return m
    return None
