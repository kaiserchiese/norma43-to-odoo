import pytest

from builders import join, one_account, r11, r22, r33, r88
from c43_to_odoo import OdooPushError, parse
from c43_to_odoo.mapping import statement_lines
from c43_to_odoo.push import OdooClient, push

LINE = "account.bank.statement.line"


class FakeOdoo:
    """Records every call; answers like a minimal Odoo."""

    def __init__(self, *, journals=None, has_unique=True, existing=(), journal_currency="EUR"):
        self.calls = []
        self.journals = [{"id": 7, "name": "Bank", "currency_id": False, "company_id": [1, "Co"]}] \
            if journals is None else journals
        self.has_unique, self.existing, self.journal_currency = has_unique, list(existing), journal_currency

    def call(self, model, method, *args, **kwargs):
        self.calls.append((model, method, args, kwargs))
        if method == "fields_get":
            return {"unique_import_id": {}} if self.has_unique else {"date": {}}
        if model == "account.journal":
            return self.journals
        if model == "res.company":
            return [{"id": 1, "currency_id": [1, self.journal_currency]}]
        if method == "search_read" and model == LINE:
            return [{"unique_import_id": u} for u in self.existing]
        if method == "create":
            return list(range(100, 100 + len(args[0])))
        raise AssertionError(f"unexpected call {model}.{method}")

    def writes(self):
        return [c for c in self.calls if c[1] in ("create", "write", "unlink")]


@pytest.fixture
def accounts():
    return parse(join(*one_account()))


def test_dry_run_never_writes(accounts):
    fake = FakeOdoo()
    report = push(accounts, client=fake)
    assert fake.writes() == []
    assert (report.accounts[0].new, report.accounts[0].duplicates) == (3, 0)
    assert report.accounts[0].total_cents == 6500  # -25.00 + 100.00 - 10.00
    assert report.created_ids == []


def test_commit_is_one_create_with_all_new_lines(accounts):
    fake = FakeOdoo()
    report = push(accounts, client=fake, commit=True)
    (create,) = fake.writes()
    vals = create[2][0]
    assert len(vals) == 3 and all(v["journal_id"] == 7 for v in vals)
    assert vals[0]["amount"] == "-25.00" and vals[0]["date"] == "2026-11-03"
    assert "narration" not in vals[0]  # empty values are not sent
    assert report.created_ids == [100, 101, 102]


def test_existing_ids_are_skipped(accounts):
    ids = [r["unique_import_id"] for r in statement_lines(accounts[0])]
    fake = FakeOdoo(existing=ids[:2])
    report = push(accounts, client=fake, commit=True)
    assert (report.accounts[0].new, report.accounts[0].duplicates) == (1, 2)
    assert len(fake.writes()[0][2][0]) == 1


def test_all_duplicates_means_no_create(accounts):
    ids = [r["unique_import_id"] for r in statement_lines(accounts[0])]
    fake = FakeOdoo(existing=ids)
    push(accounts, client=fake, commit=True)
    assert fake.writes() == []


def test_missing_unique_import_id_aborts_even_in_dry_run(accounts):
    with pytest.raises(OdooPushError, match="unique_import_id"):
        push(accounts, client=FakeOdoo(has_unique=False))


def test_no_dedup_skips_the_check_and_the_key(accounts):
    fake = FakeOdoo(has_unique=False)
    push(accounts, client=fake, commit=True, dedup=False)
    assert "unique_import_id" not in fake.writes()[0][2][0][0]


@pytest.mark.parametrize("journals", [[], [
    {"id": 1, "name": "A", "currency_id": False, "company_id": [1, "Co"]},
    {"id": 2, "name": "B", "currency_id": False, "company_id": [1, "Co"]}]])
def test_journal_zero_or_many_is_an_error(accounts, journals):
    with pytest.raises(OdooPushError, match="--journal"):
        push(accounts, client=FakeOdoo(journals=journals))


def test_journal_code_with_several_accounts_is_an_error():
    two = parse(join(r11(account="0000000001"), r33(account="0000000001"),
                     r11(account="0000000002"), r33(account="0000000002"), r88(4)))
    with pytest.raises(OdooPushError, match="one account"):
        push(two, client=FakeOdoo(), journal_code="BNK")


def test_journal_is_found_by_account_pattern(accounts):
    fake = FakeOdoo()
    push(accounts, client=fake)
    domain = next(c for c in fake.calls if c[0] == "account.journal")[2][0]
    assert ["bank_account_id.sanitized_acc_number", "=like", "ES__99990001__0000000001"] in [list(t) for t in domain]


def test_currency_mismatch_is_an_error():
    usd = parse(join(r11(currency="840"), r33(currency="840"), r88(3)))
    with pytest.raises(OdooPushError, match="currency"):
        push(usd, client=FakeOdoo())


def test_zero_movement_account_is_fine():
    empty = parse(join(r11(), r33(), r88(3)))
    report = push(empty, client=FakeOdoo(), commit=True)
    assert report.accounts[0].new == 0


def test_api_key_never_appears_in_repr():
    client = OdooClient("https://odoo.invalid", "db", "user@example.test", "s3cret-key")
    assert "s3cret-key" not in repr(client)


def test_from_env_requires_all_variables(monkeypatch):
    for name in ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(OdooPushError, match="ODOO_DB"):
        OdooClient.from_env(url="https://odoo.invalid")


@pytest.mark.parametrize("url", ["http://odoo.example.com", "ftp://odoo.example.com", "odoo.example.com"])
def test_client_refuses_a_remote_url_that_is_not_https(url):
    # The API key travels in every call: over plain http anyone on the path can read it.
    with pytest.raises(OdooPushError, match="https"):
        OdooClient(url, "db", "user", "key")


@pytest.mark.parametrize("url", ["https://odoo.example.com", "http://127.0.0.1:8069", "http://localhost:8069"])
def test_client_accepts_https_and_loopback_http(url):
    OdooClient(url, "db", "user", "key")
