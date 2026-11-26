# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub:
**[Security → Report a vulnerability](https://github.com/makaDv/DualVault/security/advisories/new)**
(GitHub Private Vulnerability Reporting).

Please include:

- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- the DualVault version, OS and Python version.

You can expect an initial response within 7 days. Once a fix is available, a
security advisory will be published and you will be credited unless you prefer
to stay anonymous.

## Scope

In scope: the DualVault code in this repository (backup creation, encryption,
restore/extraction, scheduling, rclone invocation).

Out of scope: vulnerabilities in rclone, Python, or third-party packages
(report them upstream), and issues requiring an attacker who already controls
the user's account.

## Security notes for users

- Keep your encryption password safe: lost passwords cannot be recovered.
- If you use `password_file` for unattended backups, restrict its permissions
  and do not store it on the backup destinations.
- Never share your configuration or log files publicly without checking them
  for personal paths first.
