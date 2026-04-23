"""Per-doc-type extraction prompts.

The LLM response schema is provided via `call_*(schema=...)`, so here we
only need a short instruction string.
"""


def build_extract_prompt(doc_type, content=""):
    return (
        f"Extract structured fields from this Indian medical document "
        f"(type: {doc_type.value}). Return JSON matching the provided schema. "
        f"Use null for anything you cannot read; do not invent values.\n\n"
        f"Document content:\n{content or '[image - analyze visually]'}"
    )
