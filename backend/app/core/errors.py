"""Typed pipeline errors with machine-readable codes for the API/UI."""
from __future__ import annotations


class PipelineError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class InvalidFileError(PipelineError):
    def __init__(self, message: str = "The uploaded file is not a valid PDF."):
        super().__init__("INVALID_FILE", message, 422)


class NeedsPasswordError(PipelineError):
    def __init__(self, message: str = "This PDF is password protected. Enter the password to continue."):
        super().__init__("NEEDS_PASSWORD", message, 422)


class NoTransactionsError(PipelineError):
    def __init__(self, message: str = "No transactions could be extracted from this statement."):
        super().__init__("NO_TRANSACTIONS_FOUND", message, 422)


class OcrFailedError(PipelineError):
    def __init__(self, message: str = "OCR could not be completed for this scanned PDF."):
        super().__init__("OCR_FAILED", message, 422)


class TooManyPagesError(PipelineError):
    def __init__(self, message: str = "The PDF has more pages than the configured limit."):
        super().__init__("TOO_MANY_PAGES", message, 422)


class FileTooLargeError(PipelineError):
    def __init__(self, message: str = "The uploaded file exceeds the maximum allowed size."):
        super().__init__("FILE_TOO_LARGE", message, 413)
