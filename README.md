# PASION workspace
React + SCSS frontend and a Python demonstration API. Account features use the standard library; the admin document workspace has optional extraction and OCR dependencies.

Install Node.js LTS (22 or 24) and Python (3.12 recommended), then open a terminal in the project folder containing `package.json`. On Windows, run each command separately and stop if one fails:

```cmd
npm.cmd ci
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-documents.txt
npm.cmd run dev
```

This starts the frontend and backend together with the project Python environment. No PowerShell activation or Administrator terminal is required. On later runs, open **RUN-PASION.cmd** on Windows, or run `npm.cmd run dev` in the same folder. `npm run dev:full` remains an alias. Both use the fixed frontend address below, and check for an incomplete recovery, missing packages and an unusable Python environment before starting either server.

If `py` reports `Unable to create process` or `The system cannot find the file specified`, its registered Python executable is missing. Install Python 3.12 with `winget install --exact --id Python.Python.3.12` (or the official python.org Windows installer), reopen the terminal, and verify `py -3.12 --version` before creating `.venv`. If an existing Python 3.12 installation is damaged, repair it using its Windows installer. A `.venv` created on another computer is not portable; create it locally.

Vite is patched to at least 6.4.5; `package-lock.json` records the tested dependency versions. For npm versions that require install-script approval, `allowScripts` approves only the reviewed `esbuild@0.25.12` and `@parcel/watcher@2.6.0` versions. Other packages and future versions require separate review. Funding messages are optional donation notices and do not block the app. Use `npm audit` to check current advisories; avoid forced upgrades without compatibility checks.

For separate terminals, use `npm run dev:frontend` and `.\.venv\Scripts\python.exe -X utf8 backend/server.py`. Keep only one backend running on port 8000; a second instance reports that the port is already occupied. Restart the backend after changing Python code. The frontend also refuses an occupied port rather than switching to a different browser storage origin.
Open http://127.0.0.1:5173.

Upgrading from an older local project? Keep the latest source and recover a coherent database set into a **new complete folder** with `RECOVER-BACKEND.cmd`; see [BACKEND-RECOVERY.md](BACKEND-RECOVERY.md). For reviewing several source versions in a large ZIP, `PREPARE-RECOVERY.cmd` creates a smaller source-only archive; see [RECOVERY-BUNDLE.md](RECOVERY-BUNDLE.md). Private databases and credentials stay on your machine.

Signed-out visitors see the Slate & Ice public homepage. Client Login opens /#login and Get Started opens /#register. Signed-in visitors continue directly to their research workspace. The supplied PASION image and local architectural photographs are preserved. Inter and Libre Baskerville fonts are bundled locally, with licenses in public/fonts. Public portfolio figures and insights are explicitly illustrative; the allocation preview totals 100%. The same palette extends through login, account settings, and the workspace.

Demo login: demo@solvai.com / SolvAI2024!
Requires Node.js and Python 3.10 or later.

Register with your name, email, and a password of at least 8 characters, then sign in. Accounts are stored in backend/accounts.sqlite3 with salted PBKDF2 password hashes.
Set SOLVAI_EMAIL and SOLVAI_PASSWORD to override demo credentials.
This is a local demo, not production authentication.
After signing in, choose Change password and enter your current password plus a new password of at least 8 characters. Other sessions are signed out after the change. The demo account also supports changing its password; its updated password is then stored in the local accounts database.

Build with npm run build.

Forgot password works without signing in: request a six-digit email code, then submit that code with a new password. Codes expire in 10 minutes, allow five guesses, and are single-use. Requests have a 60-second resend cooldown and IP limits. Password resets sign out existing sessions. Changing a password also invalidates previously issued codes.

Real email delivery requires SMTP configuration. Run python backend/configure_email.py in a local terminal and enter your sender email plus its SMTP app password (hidden prompt). Defaults are Gmail SMTP over SSL on port 465. Use a Google app password, not your PASION password. Credentials are saved in backend/mail-config.json, which is excluded from Git. No restart is needed after configuring email. You can instead supply SMTP_HOST, SMTP_PORT, SMTP_SECURITY, SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM environment variables. Delivery errors are shown honestly; codes are never returned to the browser or printed in logs.
The protected owner account is eyyubxankisiyev@gmail.com. Use Add administrator in the dashboard to promote an active registered account. Admin access can be removed from other administrators; removing access signs them out. All administrators can manage accounts and grant admin access. Disabled accounts receive an explicit disabled-account message when signing in with the correct password. Signing in opens the account management page at /#admin. Admins can search accounts, edit names, enable or disable members, reset passwords, and delete members. Disabled/deleted accounts and accounts with reset passwords lose their sessions. Admin privileges are checked on the server and cannot be assigned during registration. The owner account cannot be disabled, deleted, or demoted; use Change password for its own password. Initial admin credentials are stored as a salted hash in the local database, not in the frontend or source code.
The Unsplash skyscraper photograph substitutes for the reference photo.
Replace the background URL in src/styles.scss with your original for an exact match.

After sign-in, all users land on the PASION home dashboard. The sidebar opens Home, Research, Watchlist, Markets, News, Assistant, account settings, and (for admins) account management. Search filters the sample companies, holdings open the company overview, and the watchlist can be edited. Dashboard prices, charts, news, macro metrics, and assistant responses are illustrative; no live market feed or AI service is connected.

The supplied original PASION logo is included at public/pasion-logo.png and shared across the login, dashboard, account settings, and admin pages.

The watchlist saves separately for each account in this browser's local storage. It supports adding and removing companies, sorting, and CSV export. Research includes ten sample companies, sector filters, company metrics, and interactive charts with four periods. News articles open in accessible dialogs; the assistant answers from the sample dataset. Press Ctrl+K (Command+K on Mac) to focus search.

Account settings show your profile and role and include password changes. The workspace adapts to mobile screens with a collapsible sidebar. Sessions are checked when the window regains focus and once per minute.

Settings and the workspace toolbar include English, Azerbaijani, Turkish, Russian, Chinese, Arabic, Vietnamese, Spanish, and French language choices, plus light and dark appearance. Preferences persist on this browser; Arabic uses a right-to-left layout. Company details open across the full screen from a holding, View company, the overview expand button, or the Full tab. The plans preview also fills the screen. Escape and the close button return to the workspace, with keyboard focus restored. Assistant and Help use the full workspace content width.

Use Change photo in Settings to upload a JPG, PNG, or WebP up to 5 MB. Photos are cropped to a centered square, resized, and saved separately for each account on this browser. The photo appears in the account card and both workspace avatars; Remove photo restores initials.

Run npm run test:ui for browser checks covering the public homepage, login/registration routes, and the complete menu, comparison exports, indicator controls, trade plans, macro and event scenarios, data reports, shared alerts, account flows, portfolio changes, bookmarks, full-screen panels, saved language and appearance preferences, and responsive layouts. These checks use Playwright Chromium and mock API responses without changing real accounts. Install the browser once with `npx playwright install chromium`; set `PLAYWRIGHT_CHANNEL=msedge` to use Microsoft Edge instead. In cloud environments with a system Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to that executable path. Run npm run test:unit for eight calculation checks covering position sizing, risk limits, moving averages, and RSI. Run python -m unittest discover -s backend for backend checks.

Home, Research, News, and Portfolio each offer five selectable views based on the supplied references. Layout choices, portfolio positions, price targets, and bookmarked news save per account on this browser. The portfolio calculates value, profit/loss, and sector exposure from editable positions and sample prices. Alerts evaluate those sample prices inside the workspace; they do not send email, push notifications, or use a live feed. Research assessment numbers and peer metrics are illustrative. News cover photos are bundled locally from Unsplash.

The PASION Pro sidebar card opens a roadmap preview. There is no subscription checkout or paid service connected.

The sidebar matches the supplied menu: Dashboard and Compare Companies, then Analytics (Stock Analytics, Indicators & VSA, Investment Research, Trade Planner, Macro Regime Monitor, Event Scenarios), then Data (Company News, Data Sources & Reports, Portfolio Risk, Watchlist & Alerts). Assistant and account controls remain below those groups. Routes use readable hashes such as /#trade-planner; earlier hashes such as /#research continue to work.

Trade Planner calculates whole-share sizing capped by both available capital and the selected risk budget. Long and short drafts validate stop and target directions, save locally, and export to CSV. It does not place orders. Stock Analytics and Indicators calculate moving averages and RSI from generated chart points. Macro and event tools expose hypothetical, simplified inputs and coefficients, not forecasts or live market signals.

The sidebar uses semantic outline icons for each tool. A branded screen remains visible while the session request is pending. Workspace navigation includes a brief 320 ms opening transition with a skeleton preview; reduced-motion users get a shorter static transition. Loading labels describe opening a view, rather than implying live market downloads.

Administrators can open Administration → Document workspace to upload PDFs, Word DOCX files, or PNG/JPEG/WebP images. Uploads save their original bytes and metadata immediately in backend/documents.sqlite3, then extract text and tables in the background. A saved document appears in the library while processing, and another upload can start immediately. The library supports filename search, PDF/Word/image filters, upload dates, newest/oldest ordering, and grouping by type, day, or month. Dates use Asia/Baku. Administrators can download saved originals, retry failed extraction, and search or ask questions with source references after extraction finishes.

Every document endpoint checks the current administrator role, including downloads and retries. Members and signed-out visitors cannot access the library. Development and preview servers block private backend folders, Event Agent state, local database files and their sidecars, environment files and recovery manifests, including files mistakenly placed under `public`. This local serving protection does not sanitize build artifacts: keep private files out of `public` before building or sharing `dist`. Original files, extracted text, tables, and processing status survive backend restarts; interrupted jobs resume automatically. Deleting a document removes its saved original and extracted content. Existing documents from the earlier database remain readable; upload an older document again to save a downloadable original.

Install document support in a project environment, then start the API with that environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-documents.txt
npm.cmd run dev:full
```

Uploads are limited to 10 MB, PDFs to 50 pages, OCR to 20 scanned pages, images to 20 megapixels, and extracted text to 200,000 characters. Uploads have a finite timeout and can be canceled. Two background workers process documents; each runs in a separate process with a 60-second hard timeout, so a stalled parser cannot block the API indefinitely. Set DOCUMENT_PROCESS_TIMEOUT to 5–300 seconds before starting the backend to adjust this limit. Failed documents retain their original for downloading and retrying. OCR can misread numbers and characters; the workspace shows extraction warnings. If OCR is unavailable on a PDF, readable native text is preserved with a warning. DOCX sections preserve document order and table cells; physical page numbers are unavailable without rendering. Convert older .doc files to DOCX or PDF before uploading.

Summaries and document questions become available after configuring an AI provider on the server. With no provider configured, local extraction and search work and AI controls explain the missing connection. Set DOCUMENT_AI_PROVIDER to ollama and DOCUMENT_AI_MODEL to the name of an installed model; OLLAMA_BASE_URL defaults to http://127.0.0.1:11434. Alternatively set DOCUMENT_AI_PROVIDER to openai, DOCUMENT_AI_MODEL to a model available in your project, and OPENAI_API_KEY. Restart the API after changing environment variables. Keys stay on the server. Questions send selected extracted excerpts to the configured provider, and responses link to valid source sections. Long-document summaries explicitly disclose when they use selected excerpts. The adapters follow the [OpenAI Responses documentation](https://developers.openai.com/api/docs/guides/text) and [Ollama generate API](https://docs.ollama.com/api/generate).


### Event Scenarios: probabilities, supporting evidence and saved reports

Choose a supported question and select **Calculate scenario probabilities**.
The server collects real public observations, constructs a complete group of
end-of-period outcomes and shows every estimate together with a 95% uncertainty
interval, the probability gap, sample sizes and later historical evaluation.
The raw probabilities sum to 100%; independently rounded labels can differ
slightly. Definition order is the default so close alternatives receive the
same treatment.

Automatic research estimates currently cover **US equity volatility (FRED
VIXCLS)** and **US mortgage rates (FRED MORTGAGE30US)**. These are symmetric
Jeffreys-smoothed historical reference rates, evaluated on later, disjoint
periods. They do not condition on today's news or establish future calibration.
The interface offers these questions explicitly; it never silently substitutes
them for Vietnam conflict risk or another unsupported selection. Unsupported
questions show the missing outcome definition, source or historical model.
See [EVENT_SERIES_RESEARCH.md](EVENT_SERIES_RESEARCH.md) for thresholds, temporal
rules, uncertainty and limitations.

Prepared models and immutable public source snapshots stay in
`backend/private-event-models/`, outside Git and source ZIPs. The server records
research forecasts before maturity and checks due forecasts against later
source snapshots when a new estimate is requested. This prospective ledger
does not automatically confer a calibrated status. Its summary is available
to signed-in users at `/api/research/events/forecast-history`.

Open **Supporting research** to collect or inspect news separately.
Research pathways use **evidence balance**, from −100 to
+100: `100 × (supporting weight − challenging weight) / all scope-eligible
story weight`. This is not an event probability or a confidence score. Both
supporting and opposing stories remain in the source notebook; unknown
language and external/unconfirmed geographic context do not add directional
support. Keyword-based direction is conservative and still requires human
review. A single story does not establish source independence.

The selected horizon sets the maturity of a forecast and, separately, the
lookback of the evidence notebook. Short-lived/long-lived research pathways are
filtered accordingly. An independently reviewed historical model catalog can
also be installed for an exact context. Without a suitable catalog or supported
automatic research model, the service withholds probabilities. Historical
experimental headline percentages stay hidden in older reports.

The complete-outcome comparison supports end-of-period distributions and
overlapping occurrence probabilities. It shows every model-defined outcome,
resolution rule, 95% interval and probability gap together, including close
alternatives. A local historical-reference estimator and later-holdout checks
are available; they do not turn headline tone into a forecast or establish
prospective calibration. See [EVENT_PROBABILITIES.md](EVENT_PROBABILITIES.md)
for the real-data requirements, explicit limitations and catalog setup.
Public outcome collection, immutable source snapshots and the remaining
coverage gaps are documented in [EVENT_OUTCOME_SOURCES.md](EVENT_OUTCOME_SOURCES.md).

Changing a filter cancels the pending request. Reports retain their original
query and timestamp; a failed refresh labels the previous report and prevents
saving it as a new analysis. Save report stores the complete snapshot in this
browser. Open it from Saved research to inspect its sources or export JSON;
local storage is not a server backup.

The source collection panel shows retrieved, filtered, accepted and regional counts,
plus individual provider results. Previously collected Event Agent snapshots and
the Company News library can be opened separately without treating archived articles
as fresh evidence. Company News distinguishes loading, request errors and empty
storage. See [NEWS-COLLECTION.md](NEWS-COLLECTION.md) for the three backend stores,
the Vietnamese feed fix, local-data recovery and optional background collection.

Automatic research preparation needs HTTPS access to `fred.stlouisfed.org`.
Public news retrieval needs HTTPS access to `news.google.com` and
`api.gdeltproject.org`, plus `www.federalreserve.gov` for monetary topics and
`mykn.kuehne-nagel.com` for Vietnam port reports. Missing feeds are reported as
unavailable; no articles or probabilities are fabricated. Regression checks:
`.venv/bin/python -m unittest discover -s backend -p 'test_event*.py'`,
`npm run test:unit`, and `npm run test:ui -- tests/f10.spec.js`.
