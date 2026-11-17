"""Errors that carry a short code, so a message shown in the dashboard can be quoted and looked up
(see docs/error-codes.md)."""

CODE_PATTERN = r"^BT-[A-Z]+-\d{3}$"


class CodedError(ValueError):
    """An expected failure with a plain-language message and a code such as BT-PDF-002."""
    code = "BT-ERR-000"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code
