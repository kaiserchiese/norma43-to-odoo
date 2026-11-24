from builders import join, one_account, r11, r22, r23, r24, r33, r88
from c43_to_odoo import parse
from c43_to_odoo.mapping import cents_to_str, statement_lines


def rows(lines, **kw):
    (acc,) = parse(join(*lines))
    return statement_lines(acc, **kw)


def test_cents_to_str():
    assert cents_to_str(-2500) == "-25.00"
    assert cents_to_str(5) == "0.05"
    assert cents_to_str(-5) == "-0.05"
    assert cents_to_str(0) == "0.00"
    assert cents_to_str(123456789012345) == "1234567890123.45"


def test_basic_row_signs_dates_and_label():
    out = rows(one_account())
    assert [r["amount"] for r in out] == ["-25.00", "100.00", "-10.00"]
    assert out[0]["date"] == "2026-11-03"
    assert out[0]["payment_ref"] == "PROVEEDOR FICTICIO SA RECIBO 0042"
    assert out[1]["payment_ref"] == "CLIENTE DE PRUEBA SL FACTURA 7"


def test_date_field_value_uses_value_date():
    assert rows(one_account(), date_field="value")[0]["date"] == "2026-11-04"


def test_payment_ref_falls_back_to_concept_label_then_slash():
    lines = [r11(), r22(concept="17", key="1", amount=100), r22(concept="77", key="1", amount=100),
             r33(debit_n=2, debit_total=200, closing=99800), r88(4)]
    out = rows(lines)
    assert out[0]["payment_ref"] != "/" and out[0]["payment_ref"]
    assert out[1]["payment_ref"] == "/"


def test_ref_skips_empty_and_all_zero_parts():
    lines = [r11(), r22(doc="0000000007", ref1="000000000000", ref2="ABC"), r33(debit_n=1, debit_total=2500, closing=97500), r88(3)]
    assert rows(lines)[0]["ref"] == "0000000007 / ABC"


def test_partner_name_from_23_01_and_empty_without():
    out = rows(one_account())
    assert out[0]["partner_name"] == "PROVEEDOR FICTICIO SA"
    assert out[2]["partner_name"] == ""


def test_partner_name_sepa_debit_skips_scheme():
    text = "CORE" + "ACREEDOR FICTICIO SL".ljust(70)
    lines = [r11(), r22(), r23("01", text[:38], text[38:]), r33(debit_n=1, debit_total=2500, closing=97500), r88(4)]
    assert rows(lines)[0]["partner_name"] == "ACREEDOR FICTICIO SL"


def test_partner_name_credit_transfer_drops_trailing_code():
    text = "ORDENANTE FICTICIO SA".ljust(66) + "ES00ORDEN1"
    lines = [r11(), r22(key="2", amount=100), r23("01", text[:38], text[38:]),
             r33(credit_n=1, credit_total=100, closing=100100), r88(4)]
    assert rows(lines)[0]["partner_name"] == "ORDENANTE FICTICIO SA"


def test_foreign_amount_goes_to_escaped_narration():
    lines = [r11(), r22(key="1", amount=1000), r24("840", 12345),
             r33(debit_n=1, debit_total=1000, closing=99000), r88(4)]
    assert rows(lines)[0]["narration"] == "Importe origen 123.45 (divisa 840)"


def test_account_number_is_not_mapped():
    assert "account_number" not in rows(one_account())[0]


def twins(extra=()):
    base = [r22(key="1", amount=500), r22(key="1", amount=500)]
    n = len(base) + len(extra)
    return [r11(), *extra, *base, r33(debit_n=n, debit_total=500 * n, closing=100000 - 500 * n), r88(n + 2)]


def test_unique_id_distinguishes_twins_and_is_stable_across_overlapping_files():
    a = [r["unique_import_id"] for r in rows(twins())]
    assert a[0] != a[1]
    # A second extract that also holds an earlier, different movement still yields the same ids.
    b = [r["unique_import_id"] for r in rows(twins(extra=[r22(op="261101", val="261101", concept="17", key="1", amount=500)]))]
    assert set(a) <= set(b)


def test_unique_id_includes_the_account():
    one = rows([r11(account="0000000001"), r22(), r33(debit_n=1, debit_total=2500, closing=97500), r88(3)])
    two = rows([r11(account="0000000002"), r22(), r33(account="0000000002", debit_n=1, debit_total=2500, closing=97500), r88(3)])
    assert one[0]["unique_import_id"] != two[0]["unique_import_id"]
    assert "0000000002" in two[0]["unique_import_id"]


def test_core_prefix_is_trimmed_only_on_sepa_debits():
    credit = parse(join(r11(), r22(key="2", amount=500), r23("01", "CORESA INGENIERIA SL"),
                        r33(credit_n=1, credit_total=500, closing=100500), r88(5)))
    assert statement_lines(credit[0])[0]["partner_name"] == "CORESA INGENIERIA SL"
