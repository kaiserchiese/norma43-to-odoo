import pytest

from builders import join, one_account, r11, r22, r33, r88
from c43_to_odoo import cli
from test_push import FakeOdoo


@pytest.fixture
def n43(tmp_path):
    path = tmp_path / "extract.c43"
    path.write_bytes(join(*one_account()))
    return path


def two_accounts(tmp_path):
    path = tmp_path / "two.c43"
    path.write_bytes(join(r11(account="0000000001"), r33(account="0000000001"),
                          r11(account="0000000002"), r33(account="0000000002"), r88(4)))
    return path


def test_csv_written_with_journal(n43, tmp_path, capsys):
    out = tmp_path / "out.csv"
    assert cli.main([str(n43), "--csv", str(out), "--journal", "Bank"]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and lines[0].endswith("journal_id") and lines[1].endswith(",Bank")
    assert "3 lines" in capsys.readouterr().out


def test_csv_without_journal_is_a_usage_error(n43, tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main([str(n43), "--csv", str(tmp_path / "o.csv")])
    assert exc.value.code == 2


def test_nothing_to_do_is_a_usage_error(n43):
    with pytest.raises(SystemExit) as exc:
        cli.main([str(n43)])
    assert exc.value.code == 2


def test_several_accounts_need_a_journal_each_and_get_one_file_each(tmp_path):
    src, out = two_accounts(tmp_path), tmp_path / "o.csv"
    assert cli.main([str(src), "--csv", str(out), "--journal", "Bank"]) == 1
    args = [str(src), "--csv", str(out), "--journal", "99990001" + "0000000001=A",
            "--journal", "99990001" + "0000000002=B"]
    assert cli.main(args) == 0
    for suffix in ("0000000001", "0000000002"):  # no movements: header only
        text = (tmp_path / f"o-99990001{suffix}.csv").read_text(encoding="utf-8")
        assert text.startswith("date,") and text.count("\n") == 1


def test_format_error_exits_1_with_line_and_no_traceback(tmp_path, capsys):
    bad = tmp_path / "bad.c43"
    bad.write_bytes(b"x" * 81 + b"\n")
    assert cli.main([str(bad), "--csv", str(tmp_path / "o.csv"), "--journal", "J"]) == 1
    err = capsys.readouterr().err
    assert "line 1" in err and "Traceback" not in err
    assert not (tmp_path / "o.csv").exists()


def test_missing_file_exits_1(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.c43"), "--csv", str(tmp_path / "o.csv"), "--journal", "J"]) == 1
    assert "nope.c43" in capsys.readouterr().err


@pytest.fixture
def fake(monkeypatch):
    odoo = FakeOdoo()

    class Stub:
        @staticmethod
        def from_env(*, url=None):
            odoo.url = url
            return odoo

    monkeypatch.setattr(cli, "OdooClient", Stub)
    return odoo


def test_odoo_url_is_a_dry_run_without_execute(n43, fake, capsys):
    assert cli.main([str(n43), "--odoo-url", "https://odoo.invalid"]) == 0
    assert fake.writes() == [] and fake.url == "https://odoo.invalid"
    assert "dry run" in capsys.readouterr().out.lower()


def test_execute_creates(n43, fake):
    assert cli.main([str(n43), "--odoo-url", "https://odoo.invalid", "--execute"]) == 0
    assert len(fake.writes()) == 1


def test_execute_without_odoo_url_is_a_usage_error(n43, tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main([str(n43), "--csv", str(tmp_path / "o.csv"), "--journal", "J", "--execute"])
    assert exc.value.code == 2


def test_push_error_exits_1(n43, fake, capsys):
    fake.has_unique = False
    assert cli.main([str(n43), "--odoo-url", "https://odoo.invalid"]) == 1
    assert "unique_import_id" in capsys.readouterr().err


def day_blocks(tmp_path):
    path = tmp_path / "days.c43"
    path.write_bytes(join(
        r11(), r22(op="261103", key="2", amount=500), r33(credit_n=1, credit_total=500, closing=100500),
        r11(opening=100500), r22(op="261104", key="2", amount=700),
        r33(credit_n=1, credit_total=700, closing=101200), r88(6)))
    return path


def test_blocks_of_the_same_account_end_up_in_one_csv(tmp_path):
    out = tmp_path / "o.csv"
    assert cli.main([str(day_blocks(tmp_path)), "--csv", str(out), "--journal", "Bank"]) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3


def test_blank_journal_does_not_touch_an_existing_csv(n43, tmp_path, capsys):
    out = tmp_path / "o.csv"
    out.write_text("keep", encoding="utf-8")
    assert cli.main([str(n43), "--csv", str(out), "--journal", ""]) == 1
    assert out.read_text(encoding="utf-8") == "keep" and "Traceback" not in capsys.readouterr().err


def test_bad_encoding_is_a_message_not_a_traceback(n43, tmp_path, capsys):
    assert cli.main([str(n43), "--csv", str(tmp_path / "o.csv"), "--journal", "J", "--encoding", "bogus"]) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_odoo_url_alone_from_env(n43, fake, monkeypatch):
    monkeypatch.setenv("ODOO_URL", "https://odoo.invalid")
    assert cli.main([str(n43)]) == 0 and fake.url == "https://odoo.invalid"


@pytest.mark.parametrize("extra", [["--journal", "J"], ["--no-dedup"], ["--odoo-journal", "X"]])
def test_flags_without_their_mode_are_usage_errors(n43, extra, monkeypatch):
    monkeypatch.delenv("ODOO_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main([str(n43), *extra])
    assert exc.value.code == 2


def test_push_with_day_blocks_and_a_journal_code(tmp_path, fake):
    src = day_blocks(tmp_path)
    assert cli.main([str(src), "--odoo-url", "https://odoo.invalid", "--odoo-journal", "BNK1", "--execute"]) == 0
    assert len(fake.writes()) == 1
