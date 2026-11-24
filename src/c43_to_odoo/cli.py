"""c43-to-odoo FILE [--csv OUT --journal NAME] [--odoo-url URL [--execute]]"""

import argparse
import os
import sys
from pathlib import Path

from .catalog import CURRENCIES
from .errors import N43Error, OdooPushError
from .export_csv import write_csv
from .mapping import statement_lines
from .model import Account, merge_blocks
from .parser import parse
from .push import OdooClient, push


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="c43-to-odoo",
        description="Read a Norma 43 file; write an Odoo CSV and/or push the lines over XML-RPC.",
        epilog="Odoo credentials come from ODOO_DB, ODOO_USER and ODOO_API_KEY (and ODOO_URL if "
               "--odoo-url is not given). They are never accepted as arguments.")
    p.add_argument("file", type=Path, help="the .c43 / .n43 file")
    p.add_argument("--csv", type=Path, metavar="OUT.csv", help="write an Odoo importer CSV")
    p.add_argument("--journal", action="append", default=[], metavar="[ACCOUNT=]NAME",
                   help="CSV journal name. With several accounts repeat it as ACCOUNT=NAME, ACCOUNT being "
                        "the 18 digits bank+branch+account")
    p.add_argument("--no-unique-id", action="store_true", help="leave unique_import_id out of the CSV")
    p.add_argument("--odoo-url", metavar="URL", help="push to this Odoo over XML-RPC (dry run by default)")
    p.add_argument("--odoo-journal", metavar="CODE", help="journal code for the push, when it cannot be found by account")
    p.add_argument("--execute", action="store_true", help="really create the lines (without it, a dry run)")
    p.add_argument("--no-dedup", action="store_true", help="push without unique_import_id (can duplicate on re-run)")
    p.add_argument("--date", choices=("operation", "value"), default="operation", dest="date_field")
    p.add_argument("--encoding", help="force the file encoding instead of detecting it")
    return p


def _key(acc: Account) -> str:
    return f"{acc.bank}{acc.branch}{acc.number}"


def _journals(accounts: tuple[Account, ...], specs: list[str]) -> dict[str, str]:
    if len(accounts) == 1 and len(specs) == 1 and "=" not in specs[0]:
        named = {_key(accounts[0]): specs[0]}
    else:
        named = dict(s.split("=", 1) for s in specs if "=" in s)
    missing = [_key(a) for a in accounts if not named.get(_key(a), "").strip()]
    if missing:
        raise OdooPushError("pass a non-empty --journal NAME (one account) or ACCOUNT=NAME for each account; "
                            f"missing {', '.join(missing)}")
    return named


def _write_csvs(accounts: tuple[Account, ...], args: argparse.Namespace) -> None:
    journals = _journals(accounts, args.journal)
    for acc in accounts:
        out = args.csv if len(accounts) == 1 else args.csv.with_name(f"{args.csv.stem}-{_key(acc)}{args.csv.suffix}")
        rows = statement_lines(acc, date_field=args.date_field)
        with out.open("w", encoding="utf-8", newline="") as fp:
            write_csv(rows, fp, journal=journals[_key(acc)], unique_id=not args.no_unique_id)
        print(f"{_key(acc)} ({CURRENCIES[acc.currency]}): {len(rows)} lines -> {out}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.csv and not args.odoo_url:
        args.odoo_url = os.environ.get("ODOO_URL")
    if not args.csv and not args.odoo_url:
        parser.error("nothing to do: give --csv and/or --odoo-url (or set ODOO_URL)")
    if args.journal and not args.csv:
        parser.error("--journal only applies with --csv (use --odoo-journal for the push)")
    if (args.odoo_journal or args.no_dedup or args.execute) and not args.odoo_url:
        parser.error("--odoo-journal, --no-dedup and --execute only apply with --odoo-url")
    if args.csv and not args.journal:
        parser.error("--csv needs --journal: without it Odoo files the lines under its first bank journal")
    try:
        accounts = merge_blocks(parse(args.file.read_bytes(), encoding=args.encoding))
        if args.csv:
            _write_csvs(accounts, args)
        if args.odoo_url:
            report = push(accounts, client=OdooClient.from_env(url=args.odoo_url), journal_code=args.odoo_journal,
                          commit=args.execute, dedup=not args.no_dedup, date_field=args.date_field)
            for r in report.accounts:
                print(f"{r.account} -> journal {r.journal!r}: {r.new} new, {r.duplicates} already there, "
                      f"net {r.total_cents / 100:.2f}")
            print(f"created {len(report.created_ids)} lines" if args.execute
                  else "Dry run: nothing written. Add --execute to create the new lines.")
    except (ValueError, LookupError, OdooPushError, OSError) as exc:  # ValueError covers N43Error and bad decoding
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
