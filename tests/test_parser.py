from datetime import date

import pytest

from builders import join, one_account, r11, r22, r23, r24, r33, r88
from c43_to_odoo import N43FormatError, N43TotalsError, parse


def test_parses_one_account_with_signed_cents():
    (acc,) = parse(join(*one_account()))
    assert (acc.bank, acc.branch, acc.number) == ("9999", "0001", "0000000001")
    assert acc.holder == "EMPRESA FICTICIA SL"
    assert (acc.opening_cents, acc.closing_cents) == (100000, 106500)
    assert [m.signed_cents for m in acc.movements] == [-2500, 10000, -1000]
    assert acc.movements[0].operation_date == date(2026, 11, 3)
    assert acc.movements[0].value_date == date(2026, 11, 4)
    assert acc.movements[0].concepts == (("01", "PROVEEDOR FICTICIO SA"), ("02", "RECIBO 0042"))


def test_amounts_are_ints_never_float():
    (acc,) = parse(join(*one_account()))
    assert all(type(m.signed_cents) is int for m in acc.movements)


def test_debtor_opening_balance_is_negative():
    lines = [r11(key="1", opening=5000), r22(key="2", amount=6000),
             r33(key="2", closing=1000, credit_n=1, credit_total=6000), r88(3)]
    (acc,) = parse(join(*lines))
    assert (acc.opening_cents, acc.closing_cents) == (-5000, 1000)


def test_several_accounts_in_one_file():
    lines = [r11(account="0000000001"), r33(account="0000000001"),
             r11(account="0000000002"), r33(account="0000000002"), r88(4)]
    accs = parse(join(*lines))
    assert [a.number for a in accs] == ["0000000001", "0000000002"]


def test_foreign_amount_record_24():
    lines = [r11(), r22(key="1", amount=1000), r24("840", 1100),
             r33(debit_n=1, debit_total=1000, closing=99000), r88(4)]
    (acc,) = parse(join(*lines))
    assert acc.movements[0].foreign.currency == "840"
    assert acc.movements[0].foreign.amount_cents == 1100


def test_zero_debit_counts_in_its_key():
    lines = [r11(), r22(key="1", amount=0), r33(debit_n=1, debit_total=0, closing=100000), r88(3)]
    (acc,) = parse(join(*lines))
    assert acc.movements[0].is_debit and acc.movements[0].signed_cents == 0


def test_short_line_is_padded_and_ctrl_z_ignored():
    raw = join(*(line.rstrip() for line in one_account()), eol="\n") + b"\x1a"
    assert len(parse(raw)[0].movements) == 3


def test_century_window():
    lines = [r11(start="991201", end="000131"), r33(), r88(2)]
    (acc,) = parse(join(*lines))
    assert (acc.start_date, acc.end_date) == (date(1999, 12, 1), date(2000, 1, 31))


@pytest.mark.parametrize("bad", ["x" * 81, "44" + " " * 78])
def test_bad_lines(bad):
    lines = one_account()
    lines.insert(1, bad)
    with pytest.raises(N43FormatError) as exc:
        parse(join(*lines))
    assert exc.value.line_no == 2


def test_error_carries_line_number_for_bad_amount():
    lines = one_account()
    lines[1] = lines[1][:28] + "1" + "ABC" + lines[1][32:]
    with pytest.raises(N43FormatError) as exc:
        parse(join(*lines))
    assert exc.value.line_no == 2


def test_22_before_11():
    with pytest.raises(N43FormatError):
        parse(join(r22(), r11(), r33(), r88(3)))


def test_23_without_22():
    with pytest.raises(N43FormatError):
        parse(join(r11(), r23(), r33(), r88(3)))


def test_more_than_five_23():
    lines = [r11(), r22()] + [r23("01")] * 6 + [r33(debit_n=1, debit_total=2500, closing=97500), r88(9)]
    with pytest.raises(N43FormatError):
        parse(join(*lines))


def test_23_data_code_out_of_range():
    lines = [r11(), r22(), r23("06"), r33(debit_n=1, debit_total=2500, closing=97500), r88(4)]
    with pytest.raises(N43FormatError):
        parse(join(*lines))


def test_two_24_records():
    lines = [r11(), r22(), r24(), r24(), r33(debit_n=1, debit_total=2500, closing=97500), r88(5)]
    with pytest.raises(N43FormatError):
        parse(join(*lines))


def test_missing_33_missing_88_trailing_garbage():
    with pytest.raises(N43FormatError):
        parse(join(r11(), r88(2)))
    with pytest.raises(N43FormatError):
        parse(join(r11(), r33()))
    with pytest.raises(N43FormatError):
        parse(join(r11(), r33(), r88(2), r11()))


def test_bad_key_and_impossible_date():
    with pytest.raises(N43FormatError):
        parse(join(r11(), r22(key="3"), r33(), r88(3)))
    with pytest.raises(N43FormatError):
        parse(join(r11(), r22(op="261332"), r33(), r88(3)))


def test_empty_file():
    with pytest.raises(N43FormatError):
        parse(b"")


def test_totals_off_by_one_cent_fail():
    lines = one_account()
    lines[-2] = r33(debit_n=2, debit_total=3501, credit_n=1, credit_total=10000, closing=106499)
    with pytest.raises(N43TotalsError):
        parse(join(*lines))


def test_counter_mismatch_fails():
    lines = one_account()
    lines[-2] = r33(debit_n=1, debit_total=3500, credit_n=2, credit_total=10000, closing=106500)
    with pytest.raises(N43TotalsError):
        parse(join(*lines))


def test_balance_equation_mismatch_fails():
    lines = one_account()
    lines[-2] = r33(debit_n=2, debit_total=3500, credit_n=1, credit_total=10000, closing=106501)
    with pytest.raises(N43TotalsError):
        parse(join(*lines))


def test_33_must_match_11_account():
    lines = one_account()
    lines[-2] = r33(account="0000000002", debit_n=2, debit_total=3500, credit_n=1,
                    credit_total=10000, closing=106500)
    with pytest.raises(N43FormatError):
        parse(join(*lines))


@pytest.mark.parametrize("delta,ok", [(0, True), (1, True), (2, False), (-1, False)])
def test_88_count_is_n_or_n_plus_1(delta, ok):
    lines = one_account()
    lines[-1] = r88(9 + delta)
    if ok:
        parse(join(*lines))
    else:
        with pytest.raises(N43FormatError):
            parse(join(*lines))


@pytest.mark.parametrize("encoding,raw_holder", [
    ("cp850", "NI\xd1O SL"), ("latin-1", "NI\xd1O SL"), ("utf-8", "NI\xd1O SL"), ("utf-8-sig", "NI\xd1O SL"),
])
def test_encodings_give_same_result(encoding, raw_holder):
    text = "\r\n".join([r11(holder=raw_holder), r33(), r88(2)]) + "\r\n"
    data = text.encode(encoding)
    (acc,) = parse(data)
    assert acc.holder == "NI\xd1O SL"


def test_u0085_byte_does_not_split_lines():
    # 0x85 is NEL when decoded as latin-1; str.splitlines() would cut the line there.
    data = join(r11(holder="A\x85B"), r33(), r88(2))
    (acc,) = parse(data)
    assert acc.holder == "A\x85B"


def test_unknown_currency_is_rejected_with_its_line():
    with pytest.raises(N43FormatError, match="line 1.*currency"):
        parse(join(r11(currency="999"), r33(currency="999"), r88(3)))


def test_file_with_no_account_is_rejected():
    with pytest.raises(N43FormatError, match="no account"):
        parse(join(r88(0)))


def test_cr_only_line_ends_are_read():
    data = b"\r".join(l.encode("latin-1") for l in one_account())
    assert len(parse(data)[0].movements) == 3
