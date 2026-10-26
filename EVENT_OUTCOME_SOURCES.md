# Historical outcome data: coverage and remaining gaps

The primary probability question is the **state at the end of the selected
period**, as requested. Each group needs measurable, mutually exclusive and
exhaustive resolution rules before it can be trained. Generic “deterioration”
and “temporary improvement” research paths are not automatically such a group.

## Implemented source adapters

`backend/event_outcome_data.py` implements these eight explicit collection
profiles. They are starting coverage, not a claim that every category,
geography or horizon already has an outcome dataset.

| Profile | Context | Source and observed measure | Important limit |
| --- | --- | --- | --- |
| `vietnam-inflation` | Vietnam inflation | World Bank `FP.CPI.TOTL.ZG`, annual CPI inflation | Annual data cannot validate daily/monthly state changes; release-vintage history is absent. |
| `vietnam-gdp` | Vietnam GDP growth | World Bank `NY.GDP.MKTP.KD.ZG`, annual real GDP growth | Latest revisions need separate treatment from first-release data. |
| `us-cpi` | US inflation | FRED `CPIAUCSL`, monthly CPI index | An index level is not an inflation rate; define and review the transformation. |
| `us-gdp` | US GDP growth | FRED `GDPC1`, quarterly real GDP level | Define the growth calculation, seasonality and release availability. |
| `us-labor` | US labor market | FRED `UNRATE`, monthly unemployment rate | A specific measure, not an adjudication of all labor conditions. |
| `us-volatility` | US equity volatility | FRED `VIXCLS`, daily implied volatility | Not realized future volatility or a generic risk probability. |
| `us-mortgages` | US mortgage rates | FRED `MORTGAGE30US`, weekly survey rate | Survey scope and release dates need review. |
| `vietnam-conflict` | Vietnam conflict | UCDP GED **25.1**, reported event fatalities with best/low/high estimates and date intervals | A fixed historical edition; sparse/missing events do not establish zero risk. It does not label every geopolitical scenario. |

The adapters use fixed HTTPS hosts, validate indicator and country identities,
preserve missing observations, reject duplicate records and incomplete pages,
and require a complete successful fetch before saving. There is no automatic
fallback to a different country, news sentiment or synthetic observations.

Each retrieval stores a new immutable snapshot, raw response bodies, SHA-256
digests, source URLs and collection time. Original observations, revisions,
UCDP uncertainty bounds and event intervals remain traceable. Failed retrievals
do not erase existing history. Collection defaults to the ignored file
`backend/private-event-models/outcomes.sqlite3`; it is separate from accounts.

These public latest-vintage endpoints **do not provide verified historical
publication timestamps for every observation**. Accordingly the collector
sets `known_at` to the actual collection time and marks every row unreviewed.
It never backdates knowledge to the observation period. Collected data is
retrospective label material, not automatic point-in-time training data or a
ready probability model. Release-vintage archives and independently reviewed
resolution rules are required before historical forecast validation.

## Collect and inspect

On Windows, run one profile at a time from the project root:

```cmd
.\.venv\Scripts\python.exe backend/event_outcome_data.py --profile vietnam-inflation
```

```cmd
.\.venv\Scripts\python.exe backend/event_outcome_data.py --profile vietnam-gdp
```

```cmd
.\.venv\Scripts\python.exe backend/event_outcome_data.py --profile vietnam-conflict
```

The same command supports each profile in the table. `--database` can select a
different private SQLite file; set `PASION_EVENT_HISTORY_PATH` to that path
when starting the API to show its coverage in the research sidebar. Reading
coverage does not create or modify the database. Observations do not silently
enable probabilities: see [EVENT_PROBABILITIES.md](EVENT_PROBABILITIES.md) for
the independent historical model review and holdout requirements.

### Current live-access status

On 23 October 2026, direct cloud requests to `api.worldbank.org`,
`fred.stlouisfed.org` and `ucdpapi.pcr.uu.se` returned proxy **HTTP 403**. The
three hostnames have been added to the cloud configuration **draft** while
preserving the existing news hosts. Saving the draft does not apply or publish
it. Live collection remains unverified until the network settings are applied
and these commands succeed. Windows network access is independent of the
cloud policy. No claim is made that an actual historical dataset has already
been retrieved or that these live endpoints were verified successfully.

## Remaining category coverage

All other contexts explicitly show that a mapped outcome source is needed.
The table below is a source/adjudication backlog, **not implemented feeds**.
It prevents the interface from implying that every selectable factor already
has a validated probability dataset.

| Category | Factors needing additional coverage or definitions | Candidate outcome evidence and work needed |
| --- | --- | --- |
| Banking & Credit | Credit conditions; Bank lending; Central bank policy | Lending surveys and volumes, archived central-bank decisions; specify survey versus decision states and release dates. |
| Business | M&A activity; Earnings outlook; Hiring plans | Completed deals, dated company filings and realized employment; distinguish announcements from completed outcomes. |
| Consumer | Consumer demand; Household spending; Consumer confidence | Official spending/retail releases and defined surveys, with revision and publication history. |
| Economy | Other regions and horizons for Inflation, GDP growth, Labor market | Region-specific national statistics, release vintages, transformation rules and frequency-compatible horizons. |
| Energy | Oil supply; Natural gas; Energy prices | Official production/inventory measures and explicitly located price series; supply, demand and price states need different rules. |
| Geopolitics | Broader Conflict risk; Sanctions; Trade disruption | Reviewed event labels, legal sanctions records and measured route/customs outcomes. Violence counts alone cannot resolve sanctions or generic conflict risk. |
| Health | Drug approvals; Healthcare costs; Public health | Dated regulator decisions, health-cost indexes and surveillance outcomes; distinguish observed outcomes from claims and reporting delays. |
| Markets | Other Equity volatility contexts; Market liquidity; Risk appetite | Defined market measures and scope; liquidity and appetite require declared observable proxies rather than latent labels. |
| Politics & Policy | Fiscal policy; Regulation; Trade policy | Archived laws, implementation/effective dates, budgets and tariff schedules with jurisdiction-specific resolution rules. |
| Real Estate | Property prices; other Mortgage rates; Commercial demand | Regional price/rate indexes and occupancy/leasing measures with publication and revision history. |
| Science | Research funding; Clinical progress; Technology adoption | Award records, registered study results and defined adoption measures; publication dates differ from the underlying event dates. |
| Technology | AI adoption; Semiconductor supply; Cybersecurity | Reviewed adoption/production measures and adjudicated incidents; missing disclosure cannot be treated as no event. |

Do not pool global cases into a Vietnam forecast just to reach a minimum
sample size. Do not turn annual measurements into hundreds of daily labels,
or split one underlying event into independent cases to inflate sample counts.
Changing the outcome family requires retraining and a genuinely independent
evaluation set. A new or rare scenario may remain unquantified while its data
coverage is built; that uncertainty must remain visible.
