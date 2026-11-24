"""Synthetic Norma 43 records. Everything is invented: bank 9999, accounts 0000000001/2."""

BANK, BRANCH = "9999", "0001"
HOLDER = "EMPRESA FICTICIA SL"


def _fit(line: str) -> str:
    assert len(line) <= 80, (len(line), line)
    return line.ljust(80)


def n(value: int, width: int) -> str:
    return str(value).zfill(width)


def r11(account="0000000001", start="261101", end="261130", key="2", opening=100000,
        currency="978", mode="3", holder=HOLDER, bank=BANK, branch=BRANCH) -> str:
    return _fit(f"11{bank}{branch}{account}{start}{end}{key}{n(opening, 14)}{currency}{mode}{holder:<26}")


def r22(op="261103", val="261104", concept="03", own="001", key="1", amount=2500,
        doc="0000000000", ref1="000000000000", ref2="", office="0001") -> str:
    return _fit(f"22    {office}{op}{val}{concept}{own}{key}{n(amount, 14)}{doc}{ref1}{ref2}")


def r23(code="01", text1="", text2="") -> str:
    return _fit(f"23{code}{text1:<38}{text2:<38}")


def r24(currency="840", amount=12345) -> str:
    return _fit(f"2401{currency}{n(amount, 14)}")


def r33(account="0000000001", debit_n=0, debit_total=0, credit_n=0, credit_total=0,
        key="2", closing=100000, currency="978", bank=BANK, branch=BRANCH) -> str:
    return _fit(f"33{bank}{branch}{account}{n(debit_n, 5)}{n(debit_total, 14)}"
                f"{n(credit_n, 5)}{n(credit_total, 14)}{key}{n(closing, 14)}{currency}")


def r88(count: int) -> str:
    return _fit(f"88{'9' * 18}{n(count, 6)}")


def join(*lines: str, eol="\r\n") -> bytes:
    return (eol.join(lines) + eol).encode("latin-1")


def one_account() -> list[str]:
    """Debit 25.00, credit 100.00, debit 10.00 on opening 1000.00 -> closing 1065.00. 88 counts 9."""
    return [
        r11(),
        r22(op="261103", val="261104", key="1", amount=2500),
        r23("01", "PROVEEDOR FICTICIO SA"),
        r23("02", "RECIBO 0042"),
        r22(op="261110", val="261110", concept="02", key="2", amount=10000),
        r23("01", "CLIENTE DE PRUEBA SL"),
        r23("02", "FACTURA 7"),
        r22(op="261115", val="261116", concept="17", key="1", amount=1000),
        r33(debit_n=2, debit_total=3500, credit_n=1, credit_total=10000, closing=106500),
        r88(9),
    ]
