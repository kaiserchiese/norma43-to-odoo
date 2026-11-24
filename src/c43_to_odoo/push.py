"""Optional XML-RPC push into account.bank.statement.line. Dry-run unless commit=True."""

import os
import http.client
import urllib.parse
import xmlrpc.client
from xml.parsers.expat import ExpatError
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol

from .catalog import CURRENCIES
from .errors import OdooPushError
from .mapping import statement_lines
from .model import Account, merge_blocks

LINE = "account.bank.statement.line"
_TRANSPORT = (xmlrpc.client.Error, OSError, ExpatError, http.client.HTTPException)
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_ENV = ("ODOO_DB", "ODOO_USER", "ODOO_API_KEY")


class Client(Protocol):
    def call(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any: ...


class OdooClient:
    """Thin xmlrpc.client wrapper. The API key is kept out of repr and error messages."""

    def __init__(self, url: str, db: str, user: str, api_key: str) -> None:
        parts = urllib.parse.urlsplit(url)
        if not (parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK)):
            raise OdooPushError("the Odoo URL must use https (plain http is allowed only for localhost): "
                                "the API key is sent with every call")
        self._url, self._db, self._user, self._key = url.rstrip("/"), db, user, api_key
        self._uid: int | None = None

    def __repr__(self) -> str:
        return f"OdooClient(url={self._url!r}, db={self._db!r}, user={self._user!r})"

    @classmethod
    def from_env(cls, *, url: str | None = None) -> "OdooClient":
        url = url or os.environ.get("ODOO_URL")
        missing = [n for n in ("ODOO_URL", *_ENV) if (n == "ODOO_URL" and not url) or (n != "ODOO_URL" and not os.environ.get(n))]
        if missing:
            raise OdooPushError(f"missing configuration: {', '.join(missing)} (credentials come from the environment only)")
        return cls(url, os.environ["ODOO_DB"], os.environ["ODOO_USER"], os.environ["ODOO_API_KEY"])  # type: ignore[arg-type]

    def _login(self) -> int:
        try:
            uid = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common").authenticate(
                self._db, self._user, self._key, {})
        except _TRANSPORT as exc:
            raise OdooPushError(f"could not reach Odoo at {self._url}: {type(exc).__name__}") from None
        if not uid:
            raise OdooPushError("Odoo rejected the credentials")
        return uid

    def call(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        if self._uid is None:
            self._uid = self._login()
        try:
            proxy = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")
            return proxy.execute_kw(self._db, self._uid, self._key, model, method, list(args), kwargs)
        except xmlrpc.client.Fault as exc:
            detail = (exc.faultString.strip().splitlines() or ["no detail"])[-1]
            raise OdooPushError(f"Odoo error on {model}.{method}: {detail}") from None
        except _TRANSPORT as exc:
            raise OdooPushError(f"call {model}.{method} failed: {type(exc).__name__}") from None


@dataclass(frozen=True)
class AccountReport:
    account: str
    journal: str
    new: int
    duplicates: int
    total_cents: int  # sum of the new lines, signed


@dataclass(frozen=True)
class PushReport:
    accounts: list[AccountReport] = field(default_factory=list)
    created_ids: list[int] = field(default_factory=list)


def _journal(client: Client, acc: Account, journal_code: str | None) -> dict:
    if journal_code:
        domain = [("type", "=", "bank"), ("code", "=", journal_code)]
    else:
        # N43 has neither the IBAN check digits nor the CCC control digits: wildcard both.
        pattern = f"ES__{acc.bank}{acc.branch}__{acc.number}"
        domain = [("type", "=", "bank"), ("bank_account_id.sanitized_acc_number", "=like", pattern)]
    found = client.call("account.journal", "search_read", domain,
                        fields=["id", "name", "currency_id", "company_id"])
    if len(found) != 1:
        raise OdooPushError(f"{len(found)} bank journals match account {acc.bank}{acc.branch}{acc.number}; "
                            "pass --journal CODE to choose one")
    return found[0]


def _check_currency(client: Client, acc: Account, journal: dict) -> None:
    wanted = CURRENCIES.get(acc.currency)
    if wanted is None:
        raise OdooPushError(f"unknown currency code {acc.currency!r} in the file")
    currency = journal["currency_id"]
    if not currency:
        company = client.call("res.company", "read", [journal["company_id"][0]], fields=["currency_id"])
        currency = company[0]["currency_id"]
    if currency[1] != wanted:
        raise OdooPushError(f"currency mismatch: file is {wanted}, journal {journal['name']!r} is {currency[1]}")


def push(
    accounts: Sequence[Account],
    *,
    client: Client,
    journal_code: str | None = None,
    commit: bool = False,
    dedup: bool = True,
    date_field: Literal["operation", "value"] = "operation",
) -> PushReport:
    accounts = merge_blocks(tuple(accounts))
    if journal_code and len(accounts) > 1:
        raise OdooPushError("--journal CODE works with one account; this file has several")
    if dedup:
        known = client.call(LINE, "fields_get", attributes=["type"])
        if "unique_import_id" not in known:
            raise OdooPushError("this Odoo has no unique_import_id on bank statement lines, so a re-import "
                                "would duplicate; install OCA account_statement_import_base or use --no-dedup")

    reports: list[AccountReport] = []
    to_create: list[dict] = []
    for acc in accounts:
        journal = _journal(client, acc, journal_code)
        _check_currency(client, acc, journal)
        rows = statement_lines(acc, date_field=date_field)
        if not dedup:
            for r in rows:
                del r["unique_import_id"]
        existing: set[str] = set()
        if dedup and rows:
            hits = client.call(LINE, "search_read", [("unique_import_id", "in", [r["unique_import_id"] for r in rows])],
                               fields=["unique_import_id"])
            existing = {h["unique_import_id"] for h in hits}
        fresh = [r for r in rows if r.get("unique_import_id") not in existing]
        to_create += [{**{k: v for k, v in r.items() if v}, "journal_id": journal["id"]} for r in fresh]
        reports.append(AccountReport(f"{acc.bank}{acc.branch}{acc.number}", journal["name"], len(fresh),
                                     len(rows) - len(fresh), _sum_cents(fresh)))

    created: list[int] = []
    if commit and to_create:
        created = list(client.call(LINE, "create", to_create))  # one call: all or nothing
    return PushReport(reports, created)


def _sum_cents(rows: list[dict[str, str]]) -> int:
    return int(sum(Decimal(r["amount"]) for r in rows) * 100)
