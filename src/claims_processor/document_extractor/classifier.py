"""Classify a document into one of the 7 claim doc types."""

from claims_processor.clients import llm_adapters
from claims_processor.models.documents import ClassifierResponse
from claims_processor.prompts.classifier_prompt import build_classifier_prompt


def classify_from_text(text):
    prompt = build_classifier_prompt(text)
    raw = llm_adapters.call_text(prompt, schema=ClassifierResponse)
    return ClassifierResponse(**raw)


def classify_from_image(image_bytes, ext):
    prompt = build_classifier_prompt()
    raw = llm_adapters.call_vision(prompt, images=[(image_bytes, ext)], schema=ClassifierResponse)
    return ClassifierResponse(**raw)
