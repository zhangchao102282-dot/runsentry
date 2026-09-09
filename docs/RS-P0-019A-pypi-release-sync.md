# RS-P0-019A PyPI Release Documentation Sync

Date: 2026-09-09

## Publication State

- PyPI package name: `runsentry`
- PyPI package URL: <https://pypi.org/project/runsentry/>
- PyPI version: `0.1.0a1`
- Related GitHub release: `v0.1.0-alpha.1`

User-reported post-publication validation from a fresh Python 3.12 virtual environment:

- `pip install runsentry`: PASS
- `runsentry --help`: PASS
- `runsentry run --help`: PASS
- `pip show runsentry`: PASS

Local note: during this documentation sync, this environment still received no matching
result from `pip index versions runsentry`, and the public project page fetch returned
404. The README was updated based on the supplied successful publication and fresh
install validation.

## README Changes

The README now presents the normal installation path first:

```bash
pip install runsentry
```

It also includes:

- a minimal quick start: `runsentry run --name demo -- python my_script.py`;
- a PyPI package link;
- the relationship between GitHub release `v0.1.0-alpha.1` and PyPI version `0.1.0a1`;
- source/development installation below the normal PyPI flow.

Removed stale README wording that said PyPI publication was planned or not yet available.

## Public Alpha Docs

Updated `docs/public-alpha.md` with the current PyPI package name, PyPI URL, PyPI
version, related GitHub release, and install command.

Updated `docs/RS-P0-018-public-trial-friction-reduction.md` by adding a later RS-P0-019A
note. The historical pre-publication facts from RS-P0-018 were preserved rather than
rewritten.

## Constraints

- Runtime code changed: no
- Package version changed: no
- New GitHub tag/release created: no
- PyPI publication performed: no
- Feature additions: no

## Validation

Commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/runsentry --help
.venv/bin/runsentry run --help
rg "pip install runsentry" README.md
```

Results:

- `.venv/bin/python -m pytest -q`: PASS, 106 passed, 3 skipped.
- `.venv/bin/runsentry --help`: PASS.
- `.venv/bin/runsentry run --help`: PASS.
- README exact install command `pip install runsentry`: PASS.

## Recommendation

Proceed to visual terminal demo recording.
