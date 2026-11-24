# Advanced Python course: source audit and acceptance checklist

Audit date: 2026-11-04. Scope: OOP, Flask, Blueprint, Jinja2, MySQL CRUD,
Flask-WTF, HTTP/REST, JSON, exception handling, email and Tkinter. This is a
source/evidence audit, **not an official lecturer rubric or grading prediction**.

Current implementation update: dataset CRUD/RBAC, safe empty SQL DELETE,
Flask-WTF dataset/upload forms and queued HTTP ingestion have superseded the
initial missing-feature findings. The expanded verifier ran 123/123 tests with
no skips; the new browser/upload E2E passed 11/11 groups, recorded separately in the
[current QA report](../releases/DATASET_UPLOAD_RELEASE_QA.md). Historical
[verification.json](verification.json) is preserved as the earlier execution,
not silently relabeled as a run of the new implementation.

## Requirement authority and scope

The accessible project and conversation attachments contain a supplied planning
Master Prompt and a follow-up project proposal. No original course handout,
assignment brief, lecturer acceptance rubric, scoring weights or official
statement about substituting Flask for Tkinter was found in that search scope.
This does not establish that such documents do not exist elsewhere.

| Source | What it establishes | What it does not establish |
|---|---|---|
| Master Prompt attachment `14cd1cb6-7377-4929-9f69-0a1dede0ffa1`, lines 5, 72-88 | Planning v1.0; explicit project technology requirements, including Flask-WTF/WTForms at line 82 | Lecturer grading rules, required marks or permission to omit a lab |
| Same attachment, lines 110-118, 165-207 | User-supplied summary of course concepts; explicitly says not to assume textbook topics are official grading requirements | Original Lab 5/Flask chapter materials or an authoritative course rubric |
| Same attachment, lines 209-217 | Tkinter is conditional on explicit lecturer requirement; Flask does not automatically satisfy Tkinter | A confirmed mandatory desktop deliverable |
| Proposal attachment `fe572890-c460-49c6-a6ef-1f8ee1fd9250`, lines 361-378 | Proposed project-to-course mapping; explicitly says it is not an official points rubric | Evidence that P0/P1 planning priorities are lecturer requirements |
| Current source and executable tests | Implementation, actual routes/packages and functional verification | Academic acceptance without the applicable requirements |
| Existing `docs/database/TRACEABILITY.md` | Historical project roadmap and source mapping | An independent primary requirement source |

Attachment identity, SHA-256 and excerpt locations are in
[sources.json](sources.json). The originals remain in the conversation attachment
store; they are not copied into the repository as purported lecturer documents.
No generic online syllabus was substituted for this student's actual course.

Three independent axes prevent misleading labels:

1. **Course mandate:** CONFIRMED only with a primary course/lecturer requirement.
   Currently **UNVERIFIED** for every listed topic's grading obligation.
2. **Project mandate:** explicit technology requirement, planned concept or
   conditional extension in the supplied project documents. These remain valid
   project requirements, but they are not relabeled as official course rules.
3. **Implementation:** IMPLEMENTED, PARTIAL or MISSING, with verification recorded
   separately as PASS / NOT RUN. A missing package is not automatically a failed
   course criterion; passing functional tests is not automatically a course pass.

## Topic-by-topic traceability

Line references describe this audited checkout; source changes can move them.

| Topic | Mandatory classification | Current implementation | Concrete source and evidence | Remaining proof / gap |
|---|---|---|---|---|
| OOP | Course UNVERIFIED; included in project/course concept mapping | IMPLEMENTED | `app/models.py:26` UTCDateTime subclasses TypeDecorator and overrides bind/result conversion; Identity/Scoped inheritance at 62/66; `app/extensions.py:9` declarative Base; frozen BGLRecord at `app/parsers/bgl.py:11` | Lecturer expectations for inheritance, polymorphism or a separate class diagram are not supplied; do not invent mandatory class names |
| Flask | Course UNVERIFIED; PROJECT-REQUIRED, Master section 3 | IMPLEMENTED | `app/__init__.py:16` application factory; configured routes and optional database wiring; actual rendered HTTP responses | Native macOS deployment is not verified by Windows tests |
| Blueprint | Course UNVERIFIED; project roadmap/chapter-7 mapping | IMPLEMENTED | Factory/database/security registration, including the existing analysis/log/alert modules and new datasets, forms and uploads blueprints | Blueprint registration is exercised by factory/API tests; the initial six-blueprint count is historical |
| Jinja2 | Course UNVERIFIED; PROJECT-REQUIRED, Master line 81 | IMPLEMENTED | `app/__init__.py:39` render_template; `app/templates/dashboard.html:21` include; partial macros, loops, conditionals and tojson; autoescape verified | Includes/macros are present; `{% extends %}` inheritance was not found. It is not added without a specific inheritance requirement |
| MySQL Create | Course UNVERIFIED; MySQL PROJECT-REQUIRED; INSERT in course-topic summary | IMPLEMENTED | BGL batch INSERT plus `app/services/dataset_management.py` dataset creation and creator grant in one transaction | Isolated MySQL tests cover duplicate/conflict rollback and concurrent personal-source creation; retained research data is not deleted |
| MySQL Read | Course UNVERIFIED; SELECT in course-topic summary | IMPLEMENTED | `app/api/logs.py:97` scoped reads; `app/repositories.py:7` bounded UTC query; pagination/isolation integration tests | A read API does not prove full CRUD for every resource |
| MySQL Update | Course UNVERIFIED; UPDATE in course-topic summary | IMPLEMENTED | Incident changes and dataset name-only PATCH/form adapter; dataset renaming preserves input_revision | Archive remains a repository helper, not an operator CLI command; immutable source/key/ownership cannot be changed by mass assignment |
| MySQL Delete / complete dataset CRUD | Course UNVERIFIED; DELETE is listed as a course topic at Master line 174 | IMPLEMENTED for dataset metadata | `app/api/datasets.py`, `app/services/dataset_management.py`; real SQL DELETE of pristine empty metadata and ACL links, admin plus explicit dataset grant | 23 CRUD MySQL tests verify roles, cross-dataset isolation, FK/revision/state guards, rollback and narrow privileges. Populated datasets are deliberately not deletable |
| Flask-WTF / WTForms | Course UNVERIFIED; **PROJECT-REQUIRED**, Master line 82 and roadmap line 1089 | IMPLEMENTED in actual workflows | `app/forms.py`, `app/api/forms.py`, `app/api/uploads.py`; declared dependencies, dataset create/rename/delete and upload forms, signed per-form CSRF plus existing header CSRF | Pure form and guarded form/API tests pass; 11/11 current dataset/upload browser groups pass. Neither CSRF mechanism is globally disabled |
| HTTP / REST API | Course UNVERIFIED; PROJECT-REQUIRED, Master line 84 | IMPLEMENTED for the accepted dataset/import scope | Dataset GET/POST/PATCH/DELETE, bounded multipart upload/status/retry, authenticated analysis/alert APIs and JSON errors | Upload supports BGL TXT/LOG and one-column raw_line CSV, not arbitrary schemas; 202 means queued, with ingestion in an external worker |
| JSON | Course UNVERIFIED; PROJECT-REQUIRED, Master line 84 | IMPLEMENTED | request.get_json, jsonify, Jinja tojson, persisted JSON evidence/config; actual 200/400/404 JSON smoke checks and MySQL roundtrip test | Not equivalent to an unknown lecturer-defined JSON exercise |
| Exception handling | Course UNVERIFIED; listed in course/network summary | IMPLEMENTED | QueryError in `app/services/investigation.py:34`; parser decode/timestamp errors; `app/security.py:184` SQLAlchemy handler rolls back and returns redacted 503; status/error tests | Do not infer that every possible exception path was exercised |
| Email | Course UNVERIFIED; email functionality listed at Master line 205 | IMPLEMENTED with SMTP mocks | `app/services/alerts.py:116` outbox delivery, STARTTLS, optional auth, bounded retry; SMTP assertions in `tests/test_platform_mysql.py:272,350` | **External delivery NOT RUN.** smtplib/EmailMessage implementation is not Flask-Mail; no exact-library mandate verified |
| Tkinter | Course UNVERIFIED; project explicitly CONDITIONAL, Master lines 209-217 | **MISSING in project** | No project Python imports/use; the interpreter can import Tkinter/Tcl/Tk 8.6 | Installed stdlib availability is not a desktop app. GUI/display/callbacks NOT RUN; Flask UI does not satisfy Tkinter labs |

Custom login validation, role-based CSRF headers and input limits remain in
`app/security.py`. Dataset/upload browser forms now additionally use actual
FlaskForm/WTForms validation. JSON dataset mutations retain their existing
session/header-CSRF contract; they are not forced through multipart forms.
Signed form tokens are obtained from authenticated `/api/v1/forms/csrf`.

## Implementation authority and limits

The initial course-conformance audit changed documentation only because no
missing feature was verified as **lecturer-mandated**. The user's subsequent
explicit project requests authorized dataset CRUD, upload/queued ingestion and
Flask-WTF implementation. Those project gaps are now implemented and tested;
this does not establish a lecturer mandate or a course pass.

No Tkinter companion, Flask-Mail substitution, template-inheritance refactor or
decorative service-class rewrite is added from an inferred rubric. The primary
course source is still required before claiming academic conformance. The
separate [July frozen IF profile](../ml/IF_JULY_HOLDOUT.md) is an experimental
model capability, not evidence for an unknown grading criterion.

## Acceptance checklist

Checked items below are source/functional evidence, not awarded course marks.

### A. Establish the actual mandatory criteria

- [x] Locate the supplied planning sources and record their identity/checksums.
- [x] Separate explicit project requirements from summaries of class topics.
- [x] Inspect source and runtime instead of equating UI appearance with behavior.
- [ ] Obtain the original assignment/lecturer rubric or an authoritative course
  acceptance statement, including version/date and relevant clause numbers.
- [ ] Record whether individual Tkinter labs must be submitted separately, a
  desktop companion must exist, or a Flask project substitution is accepted.
- [ ] Resolve whether Flask-WTF specifically, SQL DELETE/full CRUD, Flask-Mail,
  Jinja inheritance and external email delivery are mandatory rather than examples.
- [ ] Associate each confirmed clause with implementation evidence and an
  executable demonstration; leave unknown grading weights unspecified.

### B. Implemented functionality that can be demonstrated now

- [x] Explain inheritance and method overrides in UTCDateTime/ORM Base; demonstrate
  timezone validation with the database unit tests.
- [x] Create the app through its factory, list registered Blueprints and retrieve
  rendered dashboard/Explorer pages without requiring MySQL in Demo Mode.
- [x] Render Jinja includes/macros, conditions and loops; show escaping tests and
  HTML autoescape. Do not describe includes as template inheritance.
- [x] INSERT a synthetic record/dataset in an isolated MySQL fixture, SELECT it
  within the right dataset, and UPDATE incident state with authorization.
- [x] Create/read/rename dataset metadata through role- and grant-scoped APIs;
  physically DELETE only a new pristine empty fixture, and prove populated
  dataset protection plus atomic rollback.
- [x] Submit real Flask-WTF dataset/upload forms with signed form tokens and
  header CSRF; test missing/invalid tokens, malformed fields and JSON API parity.
- [x] Validate and queue BGL-compatible HTTP uploads; exercise a separate worker,
  committed progress, retry/resume and provenance using isolated MySQL fixtures.
- [x] Demonstrate foreign-key isolation, UTC boundaries, JSON roundtrip and
  transaction rollback through guarded MySQL integration tests.
- [x] Demonstrate GET/POST/PATCH/DELETE and JSON response/error contracts through API
  tests, including invalid input, unauthorized access and missing resources.
- [x] Demonstrate SMTP outbox delivery through a mock, STARTTLS invocation,
  disabled-by-default behavior, deduplication/cooldown and bounded retry.
- [x] Record environment, commands, actual counts and PASS / NOT RUN separately.

### C. Completed project gaps and unresolved conditional criteria

- [x] **Project Flask-WTF requirement:** dependencies declared; actual dataset
  and upload forms validate submissions and signed CSRF without breaking JSON
  APIs. Browser execution must be read from its separate current QA record.
- [x] **Project dataset CRUD:** real authorized empty-metadata SQL DELETE,
  name-only UPDATE and CREATE/READ are tested with FK protection and rollback.
  This is not a promise to delete imported research logs.
- [ ] **If Tkinter is required:** implement a focused companion utility with
  actual widgets/classes/callbacks, bounded work and visible error/progress
  handling; test actual GUI launch on the supported OS. Do not replace the web UI.
- [ ] **If email delivery to an inbox is required:** configure a user-authorized
  SMTP account securely, send to an approved recipient and record the delivery
  outcome. Mock assertions alone are not inbox delivery evidence.
- [ ] **If Jinja inheritance is explicitly required:** demonstrate a real parent
  template/child extends workflow, preserving the existing workspace appearance.

### D. Close the audit without damaging existing work

- [x] Preserve existing uncommitted IF V2 source, tests and measurements.
- [x] Correct the earlier documentation claim that archive has a CLI command.
- [x] Preserve the initial documentation-only audit evidence; later explicitly
  authorized application changes are described as a separate implementation.
- [x] Do not push or merge; keep all retained test schemas/data intact.
- [ ] Claim course conformance only after the primary criteria above are mapped
  and every confirmed mandatory item has evidence. No grade is predicted here.

## Historical verification and superseding current execution

The initial verification measurements remain in [verification.json](verification.json).
The commands are read/QA operations; the MySQL verifier provisions new guard-token
test schemas and retains them. It never resets the real BGL dataset.

```text
python -m unittest tests.test_database_unit tests.test_workspace tests.test_bgl_parser tests.test_evidence tests.test_investigation_v2 -q
python -m scripts.verify_mysql
```

At that historical audit, the first command ran 73 tests with no failures/skips.
The second requires private
MYSQL_ADMIN_URL and DATABASE_URL environment values; credentials are never
accepted as command arguments or copied into this report. Its actual results
were **63/63 PASS**, no failures/errors/skips, in 10.924 seconds including wrapper
overhead. The guarded discovery includes 56 actual MySQL tests and seven pure
artifact guards. Two new guard-token schemas were created and retained; no
existing database/table/volume was dropped. SMTP delivery was mocked.

The earlier factory smoke checks: `/` and `/?workspace=logs` returned 200 HTML;
`/api/v1/investigation` returned 200 JSON; invalid start time returned 400 JSON;
an unknown API route returned 404 JSON. Six registered Blueprints and 28 routes
were observed. HTML autoescape is enabled. Runtime packages confirm Flask-WTF
and WTForms were absent at that time; Tkinter import alone was tested without
creating a GUI. These absence/route-count findings are superseded by the current
source and must not be read as current implementation status.

Current expanded execution: **264 default tests, 153 PASS and 111 guarded SKIP**
in **15.772 seconds**; explicit isolated MySQL execution
**123/123 PASS, zero skips, 31.979 seconds** including wrapper overhead.
This total includes 111 database cases and 12 overlapping pure guards and must not be
added to the default total as distinct tests. It includes 23 dataset CRUD tests,
the form/API and upload API/worker suites and 10 frozen-IF guards/integration
tests. New dataset/upload browser execution passed **11/11 groups in 37.4725s**
with an actual 100K-line, 13,259,718-byte BGL file: 100,000 parsed and zero malformed.
Worker start to verified Explorer was **29.3605s**, including browser/UI checks,
not isolated ingestion time. The final DEMO suites passed 21+13 groups; actual
100K-data Investigation/Evidence/CSV regression passed 12 groups. No JavaScript
page errors occurred. The [current QA report](../releases/DATASET_UPLOAD_RELEASE_QA.md)
records these scopes separately; the original 63-test report is
left unchanged rather than rewritten as evidence for subsequent features.

**NOT RUN / UNVERIFIED:** official grading acceptance, external SMTP delivery,
Tkinter GUI and native macOS execution. Source review/freeze and manual defense
rehearsal remain release work. No synthetic grade, guessed
rubric weight or general claim of course completion is produced.
