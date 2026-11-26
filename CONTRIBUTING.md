# Contributing to DualVault

Thanks for your interest! Bug reports, ideas and pull requests are welcome.

## Ground rules

- Be respectful — this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Security issues: **do not** open public issues, see [SECURITY.md](SECURITY.md).
- Never include personal data (real paths, names, credentials, rclone configs,
  log files) in issues, pull requests, tests or fixtures.

## Development setup

```bash
git clone https://github.com/makaDv/DualVault.git
cd DualVault
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Add tests for any behavior change; keep the test suite green on all platforms.
3. Run `ruff check .` and `pytest` before pushing.
4. Keep runtime dependencies minimal; any new dependency must have a license
   compatible with Apache-2.0 and be added to `THIRD_PARTY_NOTICES.md`.
5. Describe *what* and *why* in the PR description.

## License of contributions

By submitting a contribution you agree that it is licensed under the
[Apache License 2.0](LICENSE), as described in its section 5, and that you have
the right to submit it.
