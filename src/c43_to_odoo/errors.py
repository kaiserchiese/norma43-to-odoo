"""Exceptions. Parse errors carry the 1-based line number of the offending record."""


class N43Error(ValueError):
    def __init__(self, message: str, line_no: int | None = None) -> None:
        super().__init__(f"line {line_no}: {message}" if line_no else message)
        self.line_no = line_no


class N43FormatError(N43Error):
    """A record is malformed or out of order."""


class N43TotalsError(N43Error):
    """Record 33 totals or balances do not match the movements."""


class OdooPushError(RuntimeError):
    """The XML-RPC push could not be completed."""
