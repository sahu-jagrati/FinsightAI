"""Application-level errors (Section 32).

Every one of these carries an HTTP status code and a machine-readable
`code` so the frontend can render a specific message instead of a generic
"something went wrong" (Section 32: "the frontend should display useful
errors instead of generic failures").
"""

from fastapi import status


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class UnsupportedFileTypeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "unsupported_file_type"


class FileTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "file_too_large"


class EmptyDocumentError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "empty_document"


class CorruptedDocumentError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "corrupted_document"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class InsufficientEvidenceError(AppError):
    """Raised by the RAG/agent layer (Section 16) — never invent an answer."""

    status_code = status.HTTP_200_OK
    code = "insufficient_evidence"
