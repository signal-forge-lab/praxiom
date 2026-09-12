# Git workflow

[English](GIT_WORKFLOW.md) | [日本語](GIT_WORKFLOW.ja.md)

Praxiom treats branches as development workflow, never as confidentiality
boundaries.

## Branches

- `main`: reviewed, stable public state.
- `develop`: integration branch for work that is already safe to disclose.
- `feature/*`: short-lived branches created from `develop` for individual
  changes and merged back through review.

Everything committed to any of these branches must be safe to publish.

## Public and private separation

The public GitHub repository contains public-safe source, tests,
documentation, fixtures, and example configuration only. Keep the following
outside this repository:

- API keys, tokens, private keys, certificates, or decrypted secrets;
- workstation-specific paths and local configuration;
- runtime logs, captures, generated local artifacts, or device-specific data;
- implementation that is intentionally internal-only.

Use ignored local files such as `.env`, `config.local.json`, or `local/` for
machine-specific configuration. Commit examples such as `.env.example` or
`config.example.json` only with non-secret placeholder values.

If internal-only implementation is required, use a separate private
repository. Do not place it on a private branch of this public repository.

## Secrets

The canonical secret store is external to this repository. Runtime code may
read injected environment/configuration values, but real secret values must
never be committed. A secret committed even briefly must be treated as
compromised and rotated before history cleanup.

## Before publishing

Before pushing a branch or merging to `main`:

1. Review the complete diff and staged files.
2. Scan source, tests, configuration, documentation, and relevant Git history
   for secrets, personal information, workstation paths, device identifiers,
   logs, and generated artifacts.
3. Run the deterministic test suite and repository boundary/provenance guards.
4. Confirm public documentation has English and Japanese counterparts.
5. Merge reviewed `develop` changes to `main`; do not use branches to hide
   private material.

The local pre-publication Praxiom history is intentionally not connected to
the public remote. Public development is performed from an independent clone
of the sanitized public repository.
