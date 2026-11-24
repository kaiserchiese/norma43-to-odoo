"""Regenerate tests/fixtures/*.n43 from the synthetic builders (all data invented).

Run: python tests/make_fixtures.py   (then review the files and the golden CSV by hand)
"""
from pathlib import Path

from builders import join, r11, r22, r23, r24, r33, r88

OUT = Path(__file__).parent / "fixtures"


def body_with_88(lines: list[str]) -> list[str]:
    return [*lines, r88(len(lines))]


def una_cuenta() -> list[str]:
    lines = [
        r11(holder="EMPRESA \xd1ANDU SL"),
        r22(op="261103", val="261104", concept="03", key="1", amount=2500, doc="0000000042"),
        r23("01", "PROVEEDOR FICTICIO SA"),
        r23("02", "RECIBO 0042"),
        r22(op="261110", val="261110", concept="02", key="2", amount=10000),
        r23("01", "CLIENTE DE PRUEBA SL"),
        r23("02", "FACTURA 7"),
        r22(op="261115", val="261116", concept="17", key="1", amount=1000),
        r22(op="261120", val="261121", concept="12", key="1", amount=1234),
        r23("01", "CORE" + "COMERCIO EJEMPLO SL".ljust(70)[:34], "".ljust(38)),
        r24("840", 1350),
    ]
    debits = [2500, 1000, 1234]
    lines.append(r33(debit_n=3, debit_total=sum(debits), credit_n=1, credit_total=10000,
                     closing=100000 + 10000 - sum(debits)))
    return body_with_88(lines)


def minimo() -> list[str]:
    return body_with_88([r11(), r33()])


def varias_cuentas() -> list[str]:
    return body_with_88([
        r11(account="0000000001"), r22(key="2", concept="02", amount=5000),
        r23("01", "INGRESO FICTICIO"),
        r33(account="0000000001", credit_n=1, credit_total=5000, closing=105000),
        r11(account="0000000002", opening=0), r33(account="0000000002", closing=0),
    ])


def dos_cuentas_dia_partido() -> list[str]:
    """Account 1 in two blocks of the same day (97500 then 107500), account 2 in between."""
    return body_with_88([
        r11(account="0000000001", start="261103", end="261103", opening=100000),
        r22(op="261103", val="261103", key="1", amount=2500), r23("01", "PROVEEDOR FICTICIO SA"),
        r33(account="0000000001", debit_n=1, debit_total=2500, closing=97500),
        r11(account="0000000002", start="261103", end="261103", opening=50000),
        r22(op="261103", val="261103", key="1", amount=1000), r23("01", "GASTO FICTICIO"),
        r22(op="261103", val="261103", concept="02", key="2", amount=3000), r23("01", "COBRO FICTICIO"),
        r33(account="0000000002", debit_n=1, debit_total=1000, credit_n=1, credit_total=3000, closing=52000),
        r11(account="0000000001", start="261103", end="261103", opening=97500),
        r22(op="261103", val="261103", concept="02", key="2", amount=10000), r23("01", "CLIENTE DE PRUEBA SL"),
        r33(account="0000000001", credit_n=1, credit_total=10000, closing=107500),
    ])


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    (OUT / "una_cuenta.n43").write_bytes(join(*una_cuenta()))
    (OUT / "una_cuenta_cp850.n43").write_bytes("\r\n".join(una_cuenta()).encode("cp850") + b"\r\n")
    (OUT / "minimo.n43").write_bytes(join(*minimo()))
    (OUT / "varias_cuentas.n43").write_bytes(join(*varias_cuentas()))
    (OUT.parent.parent / "examples" / "extracto-dos-cuentas.c43").write_bytes(join(*dos_cuentas_dia_partido()))
