# Contributing

Bug reports and small pull requests are welcome.

- Run `pip install -e ".[dev]"` and `python -m pytest` before opening a PR. New behaviour needs a test that fails without it.
- Test data must be invented. Do not attach or commit real bank statements, IBANs, names or amounts. If a real file shows a bug, reduce it to a synthetic one with `tests/builders.py` first.
- Do not copy code from GPL, LGPL or AGPL projects. This repository is MIT.
- Keep the library free of runtime dependencies.
- Money is integer cents. Do not introduce floats.
