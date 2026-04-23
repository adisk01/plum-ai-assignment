"""Field extraction for a classified document."""

from claims_processor.clients import llm_adapters
from claims_processor.models.documents import SCHEMA_FOR_DOC_TYPE
from claims_processor.prompts.extractor_prompts import build_extract_prompt


def extract_from_text(doc_type, text):
    schema = SCHEMA_FOR_DOC_TYPE[doc_type]
    prompt = build_extract_prompt(doc_type, text)
    raw = llm_adapters.call_text(prompt, schema=schema)
    return schema(**raw)


def extract_from_image(doc_type, image_bytes, ext):
    schema = SCHEMA_FOR_DOC_TYPE[doc_type]
    prompt = build_extract_prompt(doc_type)
    raw = llm_adapters.call_vision(prompt, images=[(image_bytes, ext)], schema=schema)
    return schema(**raw)
