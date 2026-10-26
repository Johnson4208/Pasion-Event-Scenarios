F01 identity hardening
======================

Existing Pasion pages, hash routes, PBKDF2 accounts, language/theme storage and
admin document services are preserved. No SolvAI identity schema is imported.

API policy
----------
All /api/admin/* and /api/finance/* routes require a current admin session before
dispatch, including future ingestion, Distribution and export routes. Research,
portfolio and trade routes require authentication. Unimplemented endpoints remain
404 after authorization; this change does not create economic engines.
GET /api/permissions reports server-derived permissions for the current account.
Role changes and disabled accounts are checked against storage on each request.
Errors retain the existing message field and add a stable error.code.

Audit and ownership
-------------------
SQLite audit_events records server-selected auth/admin/analytics action names,
timestamps, session actors and response status. It excludes request bodies,
cookies, reset codes, query strings and file paths. Login failures deliberately
have no client-claimed actor. Default request logging is suppressed to protect
private document searches. Binary downloads are separately audited.
New persistence must use security.get_owned / put_owned with a validated session,
never an owner supplied in a request. Data is isolated even from other admins and
cascades on account deletion. Existing admin documents remain admin-shared.

Production review gate (not certified by this patch)
--------------------------------------------------
Set PASION_ENV=production and PASION_ADMIN_EMAIL explicitly. Production does not
seed demo accounts and sets Secure session cookies; HTTPS must terminate at the
trusted deployment boundary. Provision the reserved owner account through trusted
deployment tooling; public registration cannot claim it. Remove any previously
seeded demo account before deploying an existing database. Store SMTP credentials
in deployment secrets. Restrict filesystem access to accounts.sqlite3 and document
originals; define encrypted backup, retention and recovery policies.

Sessions currently remain in process memory and are lost on restart. This backend
is a single-host demo service. Production identity/storage review, session scaling,
login abuse controls, durable audit retention and deployment security assessment
remain required before exposing real portfolios or economic research. No release
is promoted to production merely because regression tests pass.

Regression commands
-------------------
python -m unittest discover -s backend
npm run test:unit
npm run test:ui -- tests/landing.spec.js tests/workspace.spec.js tests/localization.spec.js tests/profile.spec.js tests/private-storage.spec.js tests/admin-documents.spec.js
npm run build

Validation evidence (13 October 2026)
------------------------------------
Python discovery: 87 tests, successful with 11 optional dependency skips.
JavaScript unit suite: 8 passed. Production build: passed (bundle size warning).
Focused F01 browser suite: all 25 passed, including admin documents, access
restrictions, language/theme persistence, account navigation and profile settings.
An existing invalid comma before &:hover in landing.scss was corrected to a
semicolon so the application could compile and browser checks could run.

The broader 30-test browser run initially passed 23 and failed 7. The admin
document failure happened while the stylesheet was broken and passes on rerun.
The other six failures remain outside F01: hidden research sector selection,
missing market breadth control, outdated research summary expectation, missing
saved-news control, Portfolio Risk navigation name and mobile layout controls.
These failures are not waived for a full platform release. Preserve this evidence
and repair the existing regression suite before analytics refactoring.

Focused F01 regression command:
npm run test:ui -- tests/f01.spec.js tests/admin-documents.spec.js tests/landing.spec.js tests/private-storage.spec.js tests/profile.spec.js --grep-invert "dark market cards"
