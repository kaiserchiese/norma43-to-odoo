"""Movement -> Odoo account.bank.statement.line values, all as strings."""

import hashlib
import html
import re
from collections import Counter
from typing import Literal

from .catalog import COMMON_CONCEPTS
from .model import Account, Movement


def cents_to_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"


def _concept_texts(m: Movement) -> list[str]:
    # Each record 23 holds two 38-character halves.
    return [half.strip() for _, text in m.concepts for half in (text[:38], text[38:]) if half.strip()]


def _payment_ref(m: Movement) -> str:
    return " ".join(_concept_texts(m)) or COMMON_CONCEPTS.get(m.common_concept, "/")


def _partner_name(m: Movement, mode: str) -> str:
    text = next((t for code, t in m.concepts if code == "01"), "")
    if not text.strip():
        return ""
    # Heuristic from Annex 4 (SEPA): debit 23-01 starts with the scheme, credit transfers end with a code.
    if m.is_debit and mode == "3" and text.startswith(("CORE", "B2B")):
        return text[4:74].strip()
    if mode == "3":
        return text[:66].strip()
    return text.strip()


def _ref(m: Movement) -> str:
    parts = (m.document, m.reference1, m.reference2)
    return " / ".join(p for p in parts if p and not re.fullmatch(r"0+", p))


def _fingerprint(m: Movement) -> str:
    fields = (m.value_date.isoformat(), m.common_concept, m.own_concept, str(m.signed_cents),
              m.document, m.reference1, m.reference2, *_concept_texts(m))
    return hashlib.sha256("\x1f".join(fields).encode("utf-8")).hexdigest()[:12]


def statement_lines(
    account: Account, *, date_field: Literal["operation", "value"] = "operation"
) -> list[dict[str, str]]:
    """One dict per movement. `k` numbers identical movements on the same day so twins get distinct ids."""
    seen: Counter[tuple[str, str]] = Counter()
    out = []
    for m in account.movements:
        day = m.operation_date.strftime("%Y%m%d")
        fp = _fingerprint(m)
        seen[(day, fp)] += 1
        label = COMMON_CONCEPTS.get(m.common_concept)
        out.append({
            "date": (m.value_date if date_field == "value" else m.operation_date).isoformat(),
            "payment_ref": _payment_ref(m),
            "amount": cents_to_str(m.signed_cents),
            "partner_name": _partner_name(m, account.mode),
            "ref": _ref(m),
            "transaction_type": f"{m.common_concept} {label}" if label else m.common_concept,
            "narration": html.escape(
                f"Importe origen {cents_to_str(m.foreign.amount_cents)} (divisa {m.foreign.currency})"
            ) if m.foreign else "",
            "unique_import_id": f"n43-{account.bank}{account.branch}{account.number}-{day}-{fp}-{seen[(day, fp)]}",
        })
    return out
