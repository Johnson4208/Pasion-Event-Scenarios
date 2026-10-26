# PASION Independent Event Intelligence Agent

A separate, process-owned public-source research memory for continuously updated Event Scenarios. No event data is placed in the users' account, portfolio, authentication, preference or chat/memory databases.

## Data isolation and guarantees

- Agent store: `event-agent-state/intelligence.sqlite3` (separate from `backend/accounts.sqlite3` and financial evidence databases). Override only via `PASION_EVENT_AGENT_DB`.
- Research watch configurations are **public topics only** (e.g. inflation in World, oil supply in Asia). Do not enter personal names, private holdings, email addresses, or account-specific query configurations.
- The independent agent is the **only writer**; the website reads its SQLite history in **read-only mode** via `GET /api/research/events/agent?category=Energy&factor=Oil%20supply&focus=World&horizon=30%20days` (requires an existing Pasion login).
- Snapshots persist across restarts, preserving previous evidence and ranked-scenario support. Each source revision includes source additions/removals and previous/current scenario ranking.
- A failed scrape appends poll status `FETCH_FAILED` and keeps last valid snapshot. Identical source content does **not** create a new version. Score drift without source changes can be refreshed later by an explicit model-versioning migration; it should not masquerade as a news event.
- The agent is **not connected to account memory**. The browser's existing personal study bookmarks are still separate local-storage UI state and are unaffected.

## Run continuously

Start Pasion and the agent together from Windows PowerShell:

```powershell
cd C:\pasion-workspace
$env:PASION_EVENT_AGENT_ENABLED = "1"
$env:PASION_EVENT_POLL_MINUTES = "30"
npm.cmd run dev:full
```

The Event Intelligence Agent runs every 30 minutes **while this command remains open and the PC stays awake**. It does not run when the computer is off. Running the agent alone:

```powershell
.\.venv\Scripts\python.exe backend/event_agent.py --once
.\.venv\Scripts\python.exe backend/event_agent.py --interval-minutes 30
```

For 24/7 monitoring, deploy the independent process on an always-on private server or a supervised Windows Scheduled Task/service. Do not run multiple pollers per database; the agent uses an SQLite lease.

Current default public-topic watchlist is ten combinations. Browser research questions not in this list show `WATCH_NOT_CONFIGURED`: they are NOT silently inserted into the agent store using the user's session. Future admin-only watchlist controls are still needed. It may take a minute or two for the first pass due to external news queries. See status and version history in the existing Event Scenarios page.

## Data and model interpretation

- Ranking is ten possibly overlapping, conditional research hypotheses. Each has a separate support index, **not a probability**.
- Agent stores only public source headlines/snippets, evidence weights, source links, provider coverage, uncalibrated 3-way research shares and ranked hypothesis outputs. This is not a full-text authenticated news warehouse.
- The Bayesian probability engine remains gated until there are verified event outcomes and validated priors/likelihood ratios. There is no guarantee that ten research support indices sum to 100%.
- Error conditions for network outages, insufficient evidence and unverified publication sources are explicit. No fabricated 90% probabilities.
- Feed rates and access rights must be respected. Default 10 public watches every 30 minutes can make up to 60 provider requests per cycle; use appropriate operating limits and monitor provider responses before production operation.

## Test

```powershell
python -m unittest discover -s backend -p test_event_agent_store.py -v
npm.cmd run build
```

This has passed isolated CI tests and production frontend build, but continuous real-world feed coverage and all-user production operations have not yet been end-to-end qualified.
