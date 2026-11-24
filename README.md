# c43-to-odoo

A small Python library and command line tool that reads Spanish Norma 43 (Cuaderno 43, C43, CSB43) bank statements and writes an Odoo statement-importer CSV, or pushes the lines to Odoo over XML-RPC. Version 0.1: tested only against synthetic files and a local fake XML-RPC server, never against a real Odoo or a real bank file.

Targets Odoo 17 and 18 (CSV for the bank statement importer, XML-RPC push; see "How it fits with Odoo" for the differences); needs Python 3.10+ and nothing else. Install with `pip install .` from a clone.

Odoo already imports Norma 43 inside Odoo through an OCA module (see the table below). This project covers the case where you want to read the file outside Odoo, with no Odoo module installed.

## See it run

```console
$ pip install .
$ c43-to-odoo examples/extracto-ficticio.c43 --csv out.csv --journal Bank
999900010000000001 (EUR): 4 lines -> out.csv
$ cat out.csv
date,payment_ref,amount,partner_name,ref,transaction_type,narration,unique_import_id,journal_id
2026-11-03,PROVEEDOR FICTICIO SA RECIBO 0042,-25.00,PROVEEDOR FICTICIO SA,0000000042,03 DOMICILIADOS - RECIBOS - LETRAS - PAGOS POR SU CTA.,,n43-999900010000000001-20261103-b1aa7bf52d9c-1,Bank
...
```

`examples/extracto-ficticio.c43` is invented: fake bank 9999, a fictitious company. `examples/extracto-ficticio.csv` is the expected output, and a test keeps the two in sync.

## Install

Python 3.10 or newer, no runtime dependencies.

```console
pip install .
```

## Usage

```console
c43-to-odoo FILE --csv OUT.csv --journal NAME
c43-to-odoo FILE --odoo-url https://odoo.example.com              # dry run
c43-to-odoo FILE --odoo-url https://odoo.example.com --execute    # creates lines
```

- `--journal` is required with `--csv`. Without a journal column, Odoo files the lines under the first bank journal without telling you. With several accounts in one file, repeat it as `--journal ACCOUNT=NAME` (ACCOUNT is the 18 digits bank + branch + account) and you get one CSV per account.
- A bank may send one block per day for the same account; the blocks are merged into one account before anything is written.
- `--date value` uses the value date instead of the operation date.
- `--encoding` forces an encoding. Otherwise the file is detected: UTF-8, then cp850 or latin-1 by counting Spanish letters.
- Odoo credentials come from `ODOO_DB`, `ODOO_USER` and `ODOO_API_KEY` (and `ODOO_URL` if you skip `--odoo-url`). They are never accepted as arguments. See `.env.example`.
- The Odoo URL must be https (http only for localhost): the API key goes with every call.
- In the CSV, free text that starts with `=`, `+`, `-` or `@` (also after spaces, after a `;`, or in full-width form) gets a leading `'` so a spreadsheet does not run it as a formula. The cost: a name like `-ACME SL` reads `'-ACME SL` in the CSV; the XML-RPC push sends it unchanged.
- The push is a dry run unless you pass `--execute`. A dry run only reads: it finds the journal, checks the currency, and counts new lines and duplicates.
- Exit codes: 0 ok, 1 bad file or push error (the message names the line), 2 wrong usage.

As a library:

```python
from c43_to_odoo import parse
from c43_to_odoo.mapping import statement_lines

for account in parse(open("extract.c43", "rb").read()):
    print(account.number, account.closing_cents, len(statement_lines(account)))
```

Amounts are integer cents inside the library and decimal text ("-25.00") in the CSV and the XML-RPC payload. Floats are never used.

## What it checks

The parser rejects the file, with a line number, when:

- a record is longer than 80 characters, or records are out of order;
- the account in record 33 differs from record 11;
- the debit and credit counts or totals in record 33 do not match the movements;
- opening balance plus movements does not equal the closing balance;
- the record count in record 88 matches neither N nor N+1 (some banks count the 88 itself).

A file with several accounts is read as several accounts.

## How it fits with Odoo

The CSV has the columns of Odoo's bank statement importer, plus `unique_import_id` to avoid duplicates on re-import. That field is not in core Odoo: it comes from the OCA module `account_statement_import_base` or from Enterprise. With OCA 17.0 the importer skips that field because it is read-only, so re-importing the same CSV duplicates the lines. With OCA 18.0 it deduplicates. `--no-unique-id` leaves the column out. The XML-RPC push looks lines up by `unique_import_id` and aborts if the field does not exist, unless you pass `--no-dedup`.

XML-RPC is deprecated in Odoo 19 and scheduled for removal in Odoo 22.

## Alternatives

| Project | What it is | Licence | When to pick it |
|---|---|---|---|
| OCA `l10n_es_account_statement_import_n43` (l10n-spain) | Odoo module that imports Norma 43 inside Odoo | AGPL-3 | You can install modules in your Odoo. Use this first. |
| OCA `account_statement_import_txt_xlsx` | Odoo module that maps arbitrary CSV and XLSX columns | AGPL-3 | Your bank gives you CSV or XLSX, not Norma 43. |
| `csb43` (PyPI) | Python library to read and write Norma 43, with its own converters | LGPL-3.0-or-later | You want a mature parser and a richer object model. |
| `sergief/norma43parser` | Small Norma 43 parser, last updated 2020 | MIT | You want a parser only and accept an old project. |
| `enricopesce/norma43` | Small Norma 43 parser | Apache-2.0 | You want a parser only. |
| c43-to-odoo | Parser, Odoo CSV, optional XML-RPC push, command line, no Odoo module | MIT | You need a command line step outside Odoo, or a remote push, and accept an early version. |

This project does not copy code from any of them. The parser was written from the public Cuaderno 43 layout. Its behaviour (the N+1 tolerance on record 88, zero-amount lines, the order of encodings tried) was checked against the OCA module `l10n_es_account_statement_import_n43` (AGPL-3); no code was copied from it.

## Limitations

- Not tested against a real Odoo or real bank files. Banks differ in small ways, so expect to adjust.
- `account_number` is not mapped. The journal decides the account.
- The partner name is a heuristic read from the first complementary record (23-01). The `CORE`/`B2B` prefix is trimmed only on debits in mode 3 (SEPA direct debits).
- A file with a line over 80 characters is rejected, not truncated.
- The old `00` header record is ignored.

## Develop

```console
pip install -e ".[dev]"
python -m pytest --cov=c43_to_odoo
python tests/make_fixtures.py   # regenerate the synthetic fixtures
```

All test data is invented. Never add a real statement, IBAN or name, not even in a fixture. See `CONTRIBUTING.md`.

## Licence

MIT, copyright 2026 kaiserchiese.
