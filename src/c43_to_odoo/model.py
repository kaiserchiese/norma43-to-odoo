from dataclasses import dataclass, replace
from datetime import date


@dataclass(frozen=True, slots=True)
class ForeignAmount:
    """Record 24: original currency amount, informational only, unsigned."""

    currency: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class Movement:
    line_no: int
    office: str
    operation_date: date
    value_date: date
    common_concept: str
    own_concept: str
    is_debit: bool
    amount_cents: int  # unsigned, >= 0; the sign lives in is_debit
    document: str
    reference1: str
    reference2: str
    concepts: tuple[tuple[str, str], ...]  # (record 23 data code, positions 5-80)
    foreign: ForeignAmount | None

    @property
    def signed_cents(self) -> int:
        return -self.amount_cents if self.is_debit else self.amount_cents


@dataclass(frozen=True, slots=True)
class Account:
    line_no: int
    bank: str
    branch: str
    number: str
    start_date: date
    end_date: date
    opening_cents: int  # signed: debtor negative, creditor positive
    closing_cents: int
    currency: str
    mode: str
    holder: str
    movements: tuple[Movement, ...]


def merge_blocks(accounts: tuple[Account, ...]) -> tuple[Account, ...]:
    """Join the 11..33 blocks of one account (a bank may send one block per day) in file order."""
    merged: dict[tuple[str, str, str, str], Account] = {}
    for acc in accounts:
        key = (acc.bank, acc.branch, acc.number, acc.currency)
        first = merged.get(key)
        merged[key] = acc if first is None else replace(
            first, end_date=acc.end_date, closing_cents=acc.closing_cents,
            movements=first.movements + acc.movements)
    return tuple(merged.values())
