"""Custom exceptions for the document extractor layer.

These carry user-facing messages so the API / workflow can surface them
verbatim without re-wording (satisfies TC001/TC002 'specific and actionable'
requirement).
"""


class DocumentExtractorError(Exception):
    """Base class for all extractor errors."""


class UnsupportedFileTypeError(DocumentExtractorError):
    def __init__(self, ext: str):
        self.ext = ext
        super().__init__(
            f"Unsupported file type '{ext}'. Accepted: .pdf, .jpg, .jpeg, .png, .webp"
        )


class WrongDocumentTypeError(DocumentExtractorError):
    """Raised when an uploaded document does not match the expected type.

    The `user_message` is intended to be shown to the member as-is.
    """

    def __init__(self, file_id: str, expected: str, got: str, user_message: str | None = None):
        self.file_id = file_id
        self.expected = expected
        self.got = got
        self.user_message = user_message or (
            f"The file you uploaded for '{file_id}' looks like a {got}, "
            f"but this claim requires a {expected}. Please re-upload the correct document."
        )
        super().__init__(self.user_message)


class UnreadableDocumentError(DocumentExtractorError):
    """Raised when a document is too blurry / damaged to extract from.

    The system must ask the member to re-upload that specific file — not
    reject the claim outright (TC002).
    """

    def __init__(self, file_id: str, reason: str, suggestion: str | None = None):
        self.file_id = file_id
        self.reason = reason
        self.suggestion = suggestion or (
            "Please re-upload a clearer photo or scan of this document. "
            "Make sure the text and amounts are fully visible."
        )
        super().__init__(f"{reason} (file_id={file_id})")


class DocumentClassificationError(DocumentExtractorError):
    """Raised when the LLM classifier cannot determine the document type."""

    def __init__(self, file_id: str, reason: str):
        self.file_id = file_id
        self.reason = reason
        super().__init__(f"Could not classify document {file_id}: {reason}")
