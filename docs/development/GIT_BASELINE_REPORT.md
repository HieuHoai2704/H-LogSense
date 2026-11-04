# Safe Git baseline — Gate 2 verified

Audit date: 2026-11-04 (Asia/Ho_Chi_Minh). **Gate 2 completed locally.**

## Current outcome

- Repository root: `D:\1)_KHUTAOSONG\2)Project\13)LogSense AI`.
- Branch: `main`.
- Baseline commit: `b12e19b4a09a621af2c4a002a4e4fa3407889b63`.
- Baseline message: `chore: establish safe LogSense AI baseline`.
- Baseline: exactly **100 files / 2,777,052 bytes** of uncompressed file content.
- Ignored original files: **4,183**. No full datasets, virtual environment, browser
  profile, private backup or runtime databases are tracked.
- No remote was added/edited and no push occurred.
- Original-file integrity: all **4,279** original files still exist; **4,278** are
  byte-identical to the private backup. The only approved original-file change
  is the root `.gitignore`, applied exactly from the approved proposal.
- Tests after the baseline commit: **50 passed**, 0.757 seconds, bytecode writes
  disabled. No application logic, dependencies or global Git configuration changed.

This report update is recorded in a separate documentation-only follow-up commit,
so the approved baseline remains immutable and the final working tree is clean.
Use `git log -2 --oneline` to identify that follow-up commit; a document cannot
embed its own final commit hash without another content update.

## Gate 2 checks and implementation

1. Rechecked absence of root/ancestor Git metadata and Git redirect variables.
   Revalidated all original source and independent backup hashes plus the four
   Gate 1 preparation files; verified all required source/docs were in the plan.
2. Reviewed 82 text/SVG files from the intended baseline, with value-safe reports.
   Only reviewed synthetic security test fixtures matched suspicious patterns.
   No real-secret blocker was found; no specialist scanner was installed.
3. Applied the approved `.gitignore`, initialized the existing root on `main`,
   set repository-local `core.autocrlf=false` and `core.safecrlf=true`, and checked
   that no active hooks or unexpected content-transforming attributes existed.
4. Native ignore checks protected env/local/raw/model/database representatives;
   required source, tests, docs, small synthetic CSV/JSON and the license remained
   trackable. The native untracked list matched the approved 100 paths exactly.
5. Staged ONLY approved literal paths through a NUL-delimited path list. Read
   every staged blob back through `git cat-file`; its SHA-256 and bytes matched
   the approved manifest and working file. No LFS pointer or newline normalization
   was substituted for an approved file.
6. Reviewed staged status/stat/diff and scanned actual staged text content for
   secrets. No file list expansion, deletion, private credential or large binary
   dataset was accepted. No source/content was changed to make tests pass.
7. Created the baseline commit above, verified its clean initial status, compared
   the entire original manifest and ran the automated suite successfully.
8. Updated only this report afterward, including the requested progress tree.
   The historical Gate 1 manifest remains an immutable record of the approved
   baseline; this report's follow-up change is the explicitly requested audit update.

### Whitespace interpretation — disclosed local exceptions

The first raw `git diff --cached --check` flagged preserved CRLF endings and five
pre-existing cosmetic locations. All were compared with the original backup.
Production source bytes were not rewritten or reformatted.

Repository-local `core.whitespace` enables `cr-at-eol` alongside ordinary whitespace
checks. `.git/info/attributes` applies only these exact exceptions:

- `data/raw/LOGHUB_LICENSE.txt`: preserve two upstream trailing spaces.
- `docs/ui/TIMELINE_V2_UI_SPEC.md`: preserve the two-space Markdown line breaks.
- `docs/benchmarks/v3/fixture-profile.txt`: preserve generated trailing blank lines.

Other whitespace checks stay enabled. With this explicit policy,
`git diff --cached --check` passed with no diagnostics before each commit.
These local attributes do not transform blob content, and are not shared as
application source. See [Git per-path whitespace attributes](https://git-scm.com/docs/gitattributes#_checking_whitespace_errors).
A future clone must apply an appropriate local policy before comparing working
bytes; the baseline commit itself retains the exact approved bytes.

## Requested project/progress tree

```text
LogSense AI/
├── app/                           Implemented Flask investigation workspace
│   ├── api/                       Timeline, results, CSV and evidence APIs
│   ├── services/                  Fixture aggregation, evidence and redaction
│   ├── templates/                 Single workspace and evidence drawer
│   └── static/                    CSS and JavaScript interactions
├── tests/                         50 automated tests pass
├── scripts/                       Dataset acquisition, QA and fixture benchmark
├── docs/
│   ├── research/                  Papers, datasets and published baselines
│   ├── ui/                        Wireframes, screenshots and verification
│   ├── architecture/              V3 proposal; implementation pending
│   ├── benchmarks/v3/             Measured fixture baseline; no 1M SQL claim
│   └── development/               Approved Git manifest and this report
├── data/raw/                      Local archives ignored; license notice tracked
├── research/papers/               Local downloaded PDFs ignored
├── .venv/                         Local Python environment ignored
├── .local/                        Local/browser/cache state ignored
└── .git/                          Local Git history; no remote/push
```

```text
Progress
├── Complete: Flask foundation and research acquisition
├── Complete: Investigation V2 timeline/filter/table/export flow
├── Complete: Evidence Drawer and synthetic-data verification
├── Complete: V3 architecture and six-anomaly fixture performance report
├── Complete: Independent verified backup and local Git baseline
└── Pending
    ├── GitHub remote/push: requires a separate explicit instruction
    ├── MySQL/SQLAlchemy persistence and real-data import
    ├── Executed detectors and original raw-log provenance
    └── Isolated 10K/100K/1M parsed-event database benchmarks
```

## Remaining limits

The secret review is heuristic and not an absolute security certification. Large
public research archives, downloaded papers, local browser state and the private
backup are deliberately outside Git. The private backup is a separate directory
on the same D: volume, so it is not protection against failure of that whole drive.
A Git baseline protects version history on
this machine; GitHub remains unchanged until an explicit remote/push task.

## Historical Gate 1 audit

The following sections are retained from the pre-approval audit. Their statements
about initialization/commit being pending describe Gate 1, not the current outcome
above. The original approved document is also preserved in the baseline commit.

## 1. Executive summary

The current project is eligible for a controlled first Git initialization after
approval. A verified independent private backup is complete. The proposed baseline
contains application source, tests, scripts, documentation/screenshots, root project
files and the small public Loghub license notice. Full datasets, environment,
browser profiles, downloaded papers and runtime/cache files are excluded.

This report is Gate 1 only. The user's task explicitly requires review of the
manifest before Gate 2 initialization/staging/commit. A GitHub URL does not override
that gate or authorize pushing.

## 2. Repository findings

Project root: `D:\1)_KHUTAOSONG\2)Project\13)LogSense AI`.
Flask factory: `app/__init__.py:create_app`.

- Git version: `2.54.0.windows.1`.
- No `.git` directory/file at the root or any ancestor through `D:\`.
- `git rev-parse`, status and worktree inspection report not a repository.
- No current branch, HEAD, tracked/staged files or local remotes exist.
- No applicable ancestor `AGENTS.md` was found.
- Existing configured Git author name/email are present; basic email syntax
  check passed. Values are intentionally omitted from this shareable report.
- Git global configuration has not been changed.
- Existing global/system settings resolve `core.autocrlf=true` and initial branch
  default `master`; Gate 2 must choose `main` explicitly without changing defaults.
  The byte-preserving baseline plan uses repository-local `core.autocrlf=false`
  before staging. Three preconfigured filter entries were found; filter commands
  were not printed. Native attribute/filter inspection belongs before staging.

Present: `app/`, `tests/`, `docs/`, `scripts/`, `data/`, `research/`, `config.py`,
`requirements.txt`, README and `.gitignore`. Planned directories such as workers,
migrations and core were not created. No `.env.example` currently exists; the app
has no configured private DB credentials to template during this task.

Original inventory before preparation: **4,279 files / 2,517,873,754 bytes**.
The private full manifest contains relative path, byte size and SHA-256 for every
original file, including ignored/local data. No secret values are in the manifest.

Remote reference: `https://github.com/HieuHoai2704/LogSense-AI.git`.
The GitHub connector returned 404, which does not establish repository absence
or visibility. Read-only `git ls-remote --symref` succeeded and advertised zero
refs, including no HEAD/branches/tags. Treat it as currently empty from this Git
transport's view, and recheck before any later history/remote decision.
No remote was added, fetched into the project or modified. Visibility is unverified.

## 3. Security findings

No current secret blocker was found in the intended baseline through custom
pattern scanning and targeted review. This is not an absolute security guarantee.
Gitleaks/TruffleHog executables were not available; nothing was installed.

Initial scan: 72 UTF-8 text candidates and five SVG design files reviewed. PNGs
are the known synthetic UI/wireframe artifacts produced by the local QA/design
scripts; they are not personal-desktop screenshots. Source/research metadata,
small synthetic exports and configuration were reviewed for credential patterns,
private key material, credential URLs, emails and personal absolute paths.

| Location | Classification | Decision |
|---|---|---|
| `tests/test_evidence.py:198` | Deliberate non-cryptographic private-key marker for redaction testing | Track as test fixture; not a usable private key |
| `tests/test_evidence.py:199` | Deliberate URL-credential test with reserved example domain | Track as test fixture |
| `tests/test_evidence.py:131`, `:132`, `:137`, `:199` | Example-domain email/redaction assertions | Track; not actual account records |
| `scripts/qa_evidence_drawer.py:188`, `:199` | Deliberate synthetic secret/email browser test | Track as QA source |
| `app/services/evidence.py:111` | Signed cursor decoding variable | Not an embedded credential |
| `config.py`, `app/__init__.py` | Demo flags; signing key generated in memory | No configured literal secret found |
| `.local/edge-preview/` | Browser profile, local databases and possible session state | Exclude entirely; private backup only; values not inspected or printed |
| `.venv/.../cacert.pem` | Dependency CA certificate bundle | Exclude with the virtual environment |

Other credential-like assignments/JWT markers in tests are deliberate public
synthetic security examples, not real credentials. No `.env`, private key file,
SQL dump or database containing real user records was found among intended files.
No credential was printed in audit output, copied into this report or modified.

The downloaded Loghub archives are public research artifacts with their included
license/citation notice. They remain local/ignored. The small notice
`data/raw/LOGHUB_LICENSE.txt` is proposed for tracking so public sample metadata
and research documentation retain that reference. No redistribution permission for
unrelated private logs is inferred.

## 4. Large-file audit and Gitignore policy

| Group | Original inventory | Proposed policy |
|---|---:|---|
| Raw research folder | 2,274,138,149 bytes | Ignore archives; track only 553-byte Loghub notice |
| `.venv/` | 209,338,448 bytes | Ignore |
| `.local/` | 17,785,122 bytes | Ignore browser profiles, backups, temporary chunks and prior local QA |
| `research/` | 13,799,129 bytes | Ignore downloaded papers/extracted text |
| `docs/` before preparation | 2,491,197 bytes | Track reviewed text, public metadata and synthetic design/QA evidence |
| App/scripts/tests/config/README | Small source and documentation | Track explicitly, excluding bytecode |

Largest examples: Thunderbird archive 2,016,100,298 bytes; HDFS archive
186,645,559 bytes; BGL archive 57,489,019 bytes. None is proposed for staging.
No existing file is deleted/moved, and no LFS/artifact-storage migration is performed.

The existing root `.gitignore` is UNCHANGED at Gate 1.
`GITIGNORE_PROPOSED.txt` is the exact proposed replacement for approval:

- Retains environment/local/cache/raw/research exclusions, with the explicit
  public license exception in the raw folder.
- Adds Python test/type/lint caches, local env variants, private signing files,
  runtime databases/dumps, model binaries and IDE/OS state.
- Preserves ordinary `.csv`, `.json`, `.sql`, model Python source and shared
  config as trackable by default; no blanket CSV/JSON/SQL or `models/` exclusion.
- Keeps small reviewed reports under `docs/benchmarks/`; ignores uncurated local
  benchmark result directories.

Native `git check-ignore` cannot run against this project without a repository.
It is deferred to Gate 2 after approved initialization and BEFORE staging. Static
pattern review checks the intended files and representative excluded paths, but
is not represented as equivalent to Git's native matcher.

## 5. Backup verification

A complete independent backup was created in a new, uniquely named sibling
directory OUTSIDE this project's future Git root. The exact private location is
provided directly to the user, not embedded in shareable commit content.

- Copy scope: all 4,279 original files, including datasets, `.venv` and `.local`.
- Source bytes: 2,517,873,754.
- SHA-256 matched for every copied file; original files were re-read afterward
  and matched the snapshot.
- Original backup payload is unchanged and no prior backup was overwritten.
- Backup root has inheritance disabled and three access rules: current account,
  SYSTEM and local Administrators. This is access restriction, not encryption.
- A private original manifest and separate checksum are outside the repository.
- Gate 1 preparation documents are additionally copied/verified into a separate
  private preparation snapshot after generation; no original backup is overwritten.

Recovery: copy individual verified files from the private payload to a separately
chosen recovery directory and compare manifest hashes before replacement. No
restore/overwrite action was performed on this working project.

## 6. Proposed staging review

The exact proposed path list is in `BASELINE_COMMIT_FILES.md`; hashes and sizes
are in `BASELINE_COMMIT_MANIFEST.json`. This is a proposal, NOT a Git index.

- Include root project files, all reviewed source/static/templates, all three test
  modules, five project scripts, design/research/architecture/benchmark documents
  and reviewed synthetic images/exports.
- Include this report, the approval manifest/path list and proposed ignore policy.
- Exclude all full datasets, virtual environments, bytecode, local browser/runtime
  databases, downloaded PDFs/text and private backup manifests/payloads.
- The root `.gitignore` has both current and APPROVED-PLAN hashes in the manifest;
  its replacement must happen only in Gate 2 after approval.
- The approval manifest lists its own path separately rather than claiming a
  self-referential SHA-256. The complete manifest's hash is kept in the private
  preparation receipt, alongside hashes for every new preparation file.

No baseline candidate exceeds 5 MiB. All content remains local; no file upload,
remote creation, public-repository creation or push was performed.

## 7. Git initialization

Not performed. Once Gate 1 is approved, recheck ancestor/root Git metadata and
original/plan hashes, apply only the approved ignore policy, then initialize the
existing root with main as its initial branch. If Git metadata appears meanwhile,
re-audit it instead of initializing again. Do not change global configuration.

After initialization, use native `git check-ignore` for protected representatives
and ensure required source/test/docs/license files are not ignored. Only then
stage exact approved paths, never blind `git add .` or `git add -A`.
Also inspect effective attributes/filters and set only repository-local
`core.autocrlf=false` for this byte-preserving baseline. Staged blobs must match
approved planned hashes; normalization or an unexpected clean filter is a reason
to stop and review, not to rewrite the source or silently accept a different blob.

## 8. Baseline commit

Not created. Current branch/HEAD: **not applicable** until Gate 2.
Approved-plan message: `chore: establish safe LogSense AI baseline`.
No remote configuration or push is part of this plan.

Before committing: verify staged hashes/byte sizes, rerun value-safe secret review,
inspect `git diff --cached --stat`, `git diff --cached --check`, and status. Stop
if any real credential/private data or unapproved change appears.

## 9. Verification

Tests are run with bytecode writes disabled; existing application/test files must
match the original backup manifest after Gate 1. Results are recorded below after
the read-only suite completes.

Read-only suite: **50 tests passed**, 0.777s. Command: `.venv/Scripts/python.exe -B -m unittest discover -s tests -v`, with `PYTHONDONTWRITEBYTECODE=1`. No source/config fixes or dependency changes were made. Detailed output remains in the private audit receipt.

Post-commit checks are deferred: confirm main/HEAD, exact tracked paths, ignored
env/raw/runtime data, clean intended status and original-file integrity except
the explicitly approved ignore replacement. No post-commit success is claimed.

## 10. Remaining risks and next steps

1. Gate 1 approval is required before any initialization, staging or commit.
2. Heuristic scanners can miss secrets; recheck the exact staged content in Gate 2.
3. Remote visibility/history remains unverified beyond zero advertised Git refs;
   connector 404 may be permissions-related. No push is authorized.
4. Protect the local private backup and retain its manifest. It contains excluded
   local state; never copy it into the repository or upload it.
5. Recheck Git identity/backup/manifest immediately before committing. New user
   changes require review and a fresh snapshot, not overwrite/reset/clean.

Gate 2 must stop on unresolved discrepancies. Forbidden destructive Git/filesystem
commands and history rewrites are not needed for this baseline.
