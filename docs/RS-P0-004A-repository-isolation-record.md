# RS-P0-004A Repository Isolation Record

## Objective

Move the accepted RunSentry project state through RS-P0-004 out of `/Users/zhangchao` and into its own standalone repository at `/Users/zhangchao/ai-lab/runsentry`, then create a clean baseline Git commit.

## Original Project Location

- `/Users/zhangchao`

RunSentry files were previously located directly under the home directory.

## New Repository Location

- `/Users/zhangchao/ai-lab/runsentry`

The target path did not exist before migration.

## Files and Directories Moved

- `pyproject.toml`
- `README.md`
- `LICENSE`
- `.gitignore`
- `src/`
- `tests/`
- `docs/`
- `.github/`

No nearby `.git` directories were moved or modified.

## Nearby Git Directories Observed

- `/Users/zhangchao/ai-lab/sentinel/.git`
- `/Users/zhangchao/ai-lab/_legacy/sentinel_local_20260504/.git`
- `/Users/zhangchao/sentinel/.git`
- `/Users/zhangchao/.codex/.tmp/plugins/.git`

These repositories were left untouched.

## Hash Verification

The following accepted files matched before and after migration:

```text
c8bc63322843e9d6f9ecb5fb998d766961037fda9011be90c14812843b7339cc  docs/RS-P0-001-specification.md
43c647a43912279a8ee7996a4d3a3ae531ce3869532f1759e7639d8cace02c25  docs/RS-P0-001A-audit.md
69bd61f1d94eca0046f65e7394c61c6e21be9e026c1ec51f500e19b15a9d6561  docs/RS-P0-002-scaffold-record.md
a7d53e0320ff5c431354dcf568be357cc144a6a8163a5c39ccf44d27a43169f7  docs/RS-P0-003-execution-record.md
c34f1926c7e6b4c1549c433d256c71767e53590cc58ae5d2e810d9e6f5eb8d69  docs/RS-P0-004-output-observation-record.md
45db55c7ef8af03d3695bae3d739c6610be2d66bbd2a0ec4abf48a899ec6e297  src/runsentry/cli.py
913feeca09bd4a98ad5476869e4608d837a2eadba59687a62ce9bb5c57103fdb  src/runsentry/execution.py
ea8cc1b1172eec25f48ab1ee3d1e4cc263d07d914ec29f0b95e327f6683fb5e3  src/runsentry/output.py
871e0020cff85b714b96e84b2a9b9829134d41a3f45f9eed3046141e5e2ac058  pyproject.toml
```

The RS-P0-004A record itself was created after migration and is included in the baseline commit.

## Git Initialization Result

- `git init` was run from `/Users/zhangchao/ai-lab/runsentry`.
- `git rev-parse --show-toplevel` returned `/Users/zhangchao/ai-lab/runsentry`.
- The initialized repository showed only RunSentry files as untracked before staging.

## Baseline Commit

- Commit message: `RunSentry P0 baseline through RS-P0-004`
- The exact baseline commit hash is reported after commit creation. It is not embedded here because adding the hash to this file would change the commit identity.

## Local Python Limitation

- Local Python: `Python 3.9.5`
- Project contract: Python `>=3.10`

The local Python limitation remains accepted. This task did not install Python, change dependencies, or weaken the project requirement.

## Unexpected Files or Conflicts

- No existing `/Users/zhangchao/ai-lab/runsentry` directory was present.
- No target merge or overwrite was needed.
- No bytecode caches were present after migration.

## Functionality Changes

None. RS-P0-004A changed repository location and Git baseline only. It did not modify RunSentry execution or output behavior.
