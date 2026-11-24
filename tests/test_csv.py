import csv
import io

import pytest

from builders import join, one_account
from c43_to_odoo import parse
from c43_to_odoo.export_csv import write_csv
from c43_to_odoo.mapping import statement_lines

EXPECTED_HEADER = "date,payment_ref,amount,partner_name,ref,transaction_type,narration,unique_import_id,journal_id"


def render(**kw):
    (acc,) = parse(join(*one_account()))
    buf = io.StringIO()
    write_csv(statement_lines(acc), buf, journal="Bank", **kw)
    return buf.getvalue().splitlines()


def test_header_and_row_shape():
    lines = render()
    assert lines[0] == EXPECTED_HEADER
    assert len(lines) == 4
    assert lines[1].startswith("2026-11-03,PROVEEDOR FICTICIO SA RECIBO 0042,-25.00,PROVEEDOR FICTICIO SA,")
    assert lines[1].endswith(",Bank")


def test_journal_is_required():
    (acc,) = parse(join(*one_account()))
    with pytest.raises(ValueError):
        write_csv(statement_lines(acc), io.StringIO(), journal="")


def test_unique_id_column_can_be_dropped():
    lines = render(unique_id=False)
    assert lines[0] == "date,payment_ref,amount,partner_name,ref,transaction_type,narration,journal_id"


def test_values_with_commas_and_quotes_are_quoted():
    buf = io.StringIO()
    write_csv([{"date": "2026-11-03", "payment_ref": 'A, "B"', "amount": "1.00", "partner_name": "",
                "ref": "", "transaction_type": "", "narration": "", "unique_import_id": "x"}], buf, journal="J")
    assert '"A, ""B"""' in buf.getvalue()


@pytest.mark.parametrize("text", ['=HYPERLINK("http://x","y")', "+1+1", "-2+3", "@SUM(A1)"])
def test_counterparty_text_cannot_start_a_spreadsheet_formula(text):
    # Record 23 text is written by the counterparty; Excel runs a cell that starts with = + - @.
    buf = io.StringIO()
    row = {"date": "2026-11-03", "payment_ref": text, "amount": "-25.00", "partner_name": text,
           "ref": "", "transaction_type": "", "narration": text, "unique_import_id": "x"}
    write_csv([row], buf, journal="Bank")
    (record,) = list(csv.DictReader(io.StringIO(buf.getvalue())))
    assert record["payment_ref"] == record["partner_name"] == record["narration"] == "'" + text
    assert record["amount"] == "-25.00"  # numbers are not text: the sign stays


@pytest.mark.parametrize(("text", "expected"), [
    (" =1+1", "' =1+1"),                # a leading space does not stop Excel
    ("\uff1d1+1", "'\uff1d1+1"),        # full-width equals sign
    ("X;=1+1;Y", "X;'=1+1;Y"),          # es-ES Excel splits a comma-free cell on ';'
    ("A;B-C; plain", "A;B-C; plain"),   # ordinary text stays untouched
])
def test_formula_guard_covers_leading_space_fullwidth_and_semicolon(text, expected):
    buf = io.StringIO()
    row = {"date": "2026-11-03", "payment_ref": text, "amount": "-25.00", "partner_name": "",
           "ref": "", "transaction_type": "", "narration": "", "unique_import_id": "x"}
    write_csv([row], buf, journal="Bank")
    (record,) = list(csv.DictReader(io.StringIO(buf.getvalue())))
    assert record["payment_ref"] == expected
