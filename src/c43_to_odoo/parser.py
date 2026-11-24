"""Norma 43 (Cuaderno 43) reader.

Grammar: (11 (22 23{0,5} 24?)* 33)+ 88. Fixed-width 80 character records, positions are
1-based in the AEB document and sliced here as [pos-1:end]. Amounts are integer cents.
"""

import re
from datetime import date

from .errors import N43FormatError, N43TotalsError
from .catalog import CURRENCIES
from .model import Account, ForeignAmount, Movement

_SPANISH = set("ÁÉÍÓÚÜÑÇáéíóúüñç")


def _decode(data: bytes, encoding: str | None) -> str:
    if encoding:
        return data.decode(encoding)
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        text = data.decode("utf-8")
        if not text.isascii():
            return text
    except UnicodeDecodeError:
        pass
    latin, dos = data.decode("latin-1"), data.decode("cp850")
    score = lambda t: sum(c in _SPANISH for c in t)  # noqa: E731
    return dos if score(dos) > score(latin) else latin


def _num(raw: str, line_no: int, what: str) -> int:
    if not re.fullmatch(r"[0-9]+", raw):
        raise N43FormatError(f"{what} must be digits, got {raw!r}", line_no)
    return int(raw)


def _date(raw: str, line_no: int, what: str) -> date:
    yy = _num(raw[:2], line_no, what) if len(raw) == 6 else None
    if yy is None:
        raise N43FormatError(f"{what} must be AAMMDD", line_no)
    year = 2000 + yy if yy < 80 else 1900 + yy  # explicit window, valid until 2079
    try:
        return date(year, _num(raw[2:4], line_no, what), _num(raw[4:6], line_no, what))
    except ValueError:
        raise N43FormatError(f"{what} {raw!r} is not a real date", line_no) from None


def _sign(key: str, line_no: int) -> int:
    if key not in ("1", "2"):
        raise N43FormatError(f"debit/credit key must be 1 or 2, got {key!r}", line_no)
    return -1 if key == "1" else 1


class _Open:
    """Mutable accumulator for the account being read; frozen into an Account at record 33."""

    def __init__(self, line_no: int, rec: str) -> None:
        self.line_no = line_no
        self.bank, self.branch, self.number = rec[2:6], rec[6:10], rec[10:20]
        self.start = _date(rec[20:26], line_no, "start date")
        self.end = _date(rec[26:32], line_no, "end date")
        self.opening = _sign(rec[32], line_no) * _num(rec[33:47], line_no, "opening balance")
        self.currency, self.mode, self.holder = rec[47:50], rec[50], rec[51:77].rstrip(" ")
        for value, what in ((self.bank, "bank"), (self.branch, "branch"), (self.number, "account")):
            _num(value, line_no, what)
        if self.currency not in CURRENCIES:
            raise N43FormatError(f"unknown currency code {self.currency!r}", line_no)
        self.movements: list[dict] = []


def _movement(line_no: int, rec: str) -> dict:
    return {
        "line_no": line_no,
        "office": rec[6:10],
        "operation_date": _date(rec[10:16], line_no, "operation date"),
        "value_date": _date(rec[16:22], line_no, "value date"),
        "common_concept": rec[22:24],
        "own_concept": rec[24:27],
        "is_debit": _sign(rec[27], line_no) < 0,
        "amount_cents": _num(rec[28:42], line_no, "amount"),
        "document": rec[42:52].rstrip(" "),
        "reference1": rec[52:64].rstrip(" "),
        "reference2": rec[64:80].rstrip(" "),
        "concepts": [],
        "foreign": None,
    }


def _close(acc: _Open, rec: str, line_no: int) -> Account:
    ident = (rec[2:6], rec[6:10], rec[10:20], rec[73:76])
    if ident != (acc.bank, acc.branch, acc.number, acc.currency):
        raise N43FormatError("record 33 does not match the account of record 11", line_no)
    debit_n, debit_sum = _num(rec[20:25], line_no, "debit count"), _num(rec[25:39], line_no, "debit total")
    credit_n, credit_sum = _num(rec[39:44], line_no, "credit count"), _num(rec[44:58], line_no, "credit total")
    closing = _sign(rec[58], line_no) * _num(rec[59:73], line_no, "closing balance")

    debits = [m["amount_cents"] for m in acc.movements if m["is_debit"]]
    credits = [m["amount_cents"] for m in acc.movements if not m["is_debit"]]
    if (len(debits), sum(debits)) != (debit_n, debit_sum):
        raise N43TotalsError(f"debit count/total {debit_n}/{debit_sum} but movements give "
                             f"{len(debits)}/{sum(debits)}", line_no)
    if (len(credits), sum(credits)) != (credit_n, credit_sum):
        raise N43TotalsError(f"credit count/total {credit_n}/{credit_sum} but movements give "
                             f"{len(credits)}/{sum(credits)}", line_no)
    if acc.opening + sum(credits) - sum(debits) != closing:
        raise N43TotalsError("opening balance plus movements does not equal the closing balance", line_no)

    movements = tuple(
        Movement(**{**m, "concepts": tuple(m["concepts"])}) for m in acc.movements
    )
    return Account(acc.line_no, acc.bank, acc.branch, acc.number, acc.start, acc.end,
                   acc.opening, closing, acc.currency, acc.mode, acc.holder, movements)


def parse(data: bytes, *, encoding: str | None = None) -> tuple[Account, ...]:
    """Parse and fully validate a Norma 43 file. Raises N43Error with a line number."""
    # Not str.splitlines(): it also cuts on U+0085, which is a legal byte (0x85) in latin-1.
    physical = _decode(data, encoding).replace("\x1a", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    accounts: list[Account] = []
    current: _Open | None = None
    last: dict | None = None  # the open 22 that 23/24 attach to
    records = 0
    finished = False

    for line_no, raw in enumerate(physical, start=1):
        line = raw.rstrip("\r")
        if not line.strip(" "):
            continue
        if len(line) > 80:
            raise N43FormatError(f"record is {len(line)} characters, the maximum is 80", line_no)
        rec, code = line.ljust(80), line[:2]
        if finished:
            raise N43FormatError("data after record 88", line_no)
        if code == "00":
            continue  # old-version header: ignored and not counted by the 88
        if code == "88":
            if current is not None:
                raise N43FormatError("record 88 before the closing record 33", line_no)
            declared = _num(rec[20:26], line_no, "record count")
            if declared not in (records, records + 1):  # some banks count the 88 itself
                raise N43FormatError(f"record 88 declares {declared} records, the file has {records}", line_no)
            finished = True
            continue
        records += 1
        if code == "11":
            if current is not None:
                raise N43FormatError("record 11 inside an open account (missing 33)", line_no)
            current, last = _Open(line_no, rec), None
        elif code == "22":
            if current is None:
                raise N43FormatError("record 22 without an open record 11", line_no)
            last = _movement(line_no, rec)
            current.movements.append(last)
        elif code == "23":
            if last is None:
                raise N43FormatError("record 23 without a record 22", line_no)
            if len(last["concepts"]) == 5:
                raise N43FormatError("more than five records 23 for one movement", line_no)
            if rec[2:4] not in ("01", "02", "03", "04", "05"):
                raise N43FormatError(f"record 23 data code must be 01-05, got {rec[2:4]!r}", line_no)
            last["concepts"].append((rec[2:4], rec[4:80].rstrip(" ")))
        elif code == "24":
            if last is None:
                raise N43FormatError("record 24 without a record 22", line_no)
            if last["foreign"] is not None:
                raise N43FormatError("two records 24 for one movement", line_no)
            last["foreign"] = ForeignAmount(rec[4:7], _num(rec[7:21], line_no, "foreign amount"))
        elif code == "33":
            if current is None:
                raise N43FormatError("record 33 without an open record 11", line_no)
            accounts.append(_close(current, rec, line_no))
            current, last = None, None
        else:
            raise N43FormatError(f"unknown record type {code!r}", line_no)

    if not finished:
        raise N43FormatError("missing closing record 88" if not current else "missing closing record 33")
    if not accounts:
        raise N43FormatError("the file holds no account (no record 11)")
    return tuple(accounts)
