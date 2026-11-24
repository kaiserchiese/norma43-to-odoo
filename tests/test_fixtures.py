import io
from pathlib import Path

from c43_to_odoo import parse
from c43_to_odoo.export_csv import write_csv
from c43_to_odoo.mapping import statement_lines

FIX = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def csv_of(path: Path) -> str:
    (acc,) = parse(path.read_bytes())
    buf = io.StringIO()
    write_csv(statement_lines(acc), buf, journal="Bank")
    return buf.getvalue()


def test_golden_csv_matches_byte_for_byte():
    # The golden file was checked by hand against the Cuaderno 43 layout and the signs.
    assert csv_of(FIX / "una_cuenta.n43") == (FIX / "una_cuenta.csv").read_text(encoding="utf-8")


def test_cp850_and_latin1_files_give_the_same_accounts():
    assert parse((FIX / "una_cuenta_cp850.n43").read_bytes()) == parse((FIX / "una_cuenta.n43").read_bytes())
    assert parse((FIX / "una_cuenta.n43").read_bytes())[0].holder == "EMPRESA \xd1ANDU SL"


def test_minimal_file_has_one_account_and_no_movements():
    (acc,) = parse((FIX / "minimo.n43").read_bytes())
    assert acc.movements == () and acc.opening_cents == acc.closing_cents == 100000


def test_several_accounts_fixture():
    first, second = parse((FIX / "varias_cuentas.n43").read_bytes())
    assert (len(first.movements), len(second.movements)) == (1, 0)
    assert second.closing_cents == 0


def test_shipped_example_stays_in_sync_with_its_expected_output():
    assert csv_of(EXAMPLES / "extracto-ficticio.c43") == (EXAMPLES / "extracto-ficticio.csv").read_text(encoding="utf-8")


def test_two_accounts_with_a_split_day_read_whole_against_control_totals():
    # Account 1 arrives as two blocks for the same day, with account 2 in between.
    # Control totals are literals worked out by hand, not recomputed from the parser.
    from c43_to_odoo.model import merge_blocks

    data = (EXAMPLES / "extracto-dos-cuentas.c43").read_bytes()
    assert len(parse(data)) == 3
    one, two = merge_blocks(parse(data))
    assert (one.number, one.opening_cents, one.closing_cents, len(one.movements)) == ("0000000001", 100000, 107500, 2)
    assert [(m.is_debit, m.amount_cents) for m in one.movements] == [(True, 2500), (False, 10000)]
    assert (two.number, two.opening_cents, two.closing_cents, len(two.movements)) == ("0000000002", 50000, 52000, 2)
    assert [(m.is_debit, m.amount_cents) for m in two.movements] == [(True, 1000), (False, 3000)]
