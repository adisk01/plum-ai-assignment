"""Extractor exceptions."""


class DocumentExtractorError(Exception):
    pass


class UnsupportedFileTypeError(DocumentExtractorError):
    def __init__(self, ext):
        self.ext = ext
        super().__init__(f"Unsupported file type: {ext}")


class WrongDocumentTypeError(DocumentExtractorError):
    def __init__(self, file_id, expected, got):
        self.file_id = file_id
        self.expected = expected
        self.got = got
        super().__init__(f"{file_id}: expected {expected}, got {got}")


class UnreadableDocumentError(DocumentExtractorError):
    def __init__(self, file_id, reason):
        self.file_id = file_id
        self.reason = reason
        super().__init__(f"{file_id}: {reason}")
