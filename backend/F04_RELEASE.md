F04 reviewed forecasts and valuation
===================================

Investment Research now defaults to reviewed models. Its model cards, method
comparison, actual financial relationships and Summary remain in the existing
screen. The previous FPT walkthrough is explicitly selected as an illustrative
sample; its BUY label and averaged-fair-value wording are removed.

API / ownership
---------------
POST /api/research/assumptions: {ticker,scenario,assumptions:[{definition,value,
unit,effective_from,source_ids,currency?}]}. Fraction 0.05 means 5%, no rate defaults.
Each saved assumption gets an immutable ID/version, owner, effective/known clocks
and ASSUMPTION origin. A new version starts UNVERIFIED. It cannot create an eligible
estimate merely by supplying a client-side reviewed flag.

POST /api/admin/finance/assumptions/review: {owner,assumption_ids}.
Admin role and existing accepted source facts for the issuer are required. Currency
assumptions must match their source currency. The admin must independently review
driver justification, peer comparability, sector classification, stable terminal
economics, recurring dividends and adjusted-asset evidence before confirming.
Referenced facts establish traceability; their existence alone does not establish
the economic truth of a forward assumption. This remains a human review gate.

POST /api/research/valuation: {ticker,period:FY|TTM,period_end?,scenario,
valuation_date,valuation_timezone?}. Default valuation timezone is Asia/Shanghai.
GET /api/research/valuation/runs/:id returns only the authenticated owner's run,
including for admins. Other users' run IDs return 404. Assumptions and run snapshots
persist in owner-scoped SQLite tables with account deletion cascades.

Model policy
------------
Industrial FCFF and FCFE require an eligible annual reviewed base, standardized
EBITDA, operating (noncash) working capital, diluted shares, verified operating
drivers, taxes, borrowing and discount-rate components. Bank/insurer policies
withhold industrial FCFF/FCFE; eligible dividend, P/E or adjusted-asset alternatives
remain separate. Classification itself requires reviewed sector_policy evidence.

Revenue, EBIT, D&A, capex, working capital and common-income forecasts form five
dated years. FCFF = EBIT - operating tax + D&A - capex - delta operating NWC.
FCFE = common income + D&A - capex - delta operating NWC + net borrowing.
Common income includes after-tax interest and minority income; no automatic tax
credit is assumed for losses. FCFF enterprise-to-equity bridge separately accounts
for debt, cash, restricted cash, lease debt, reviewed NCI value and nonoperating
value. Missing bridge entries stay missing; zero must be reported or reviewed.

Ke = risk-free + beta * ERP. WACC = Ke*(1-debt_weight) + debt_cost*(1-tax)*debt_weight.
Year-end cash flows use ACT/365 from valuation date. Terminal rates must exceed
growth, terminal cash must be positive and stable economics must be reviewed.
No stale annual base whose first projected cash date is already past is enabled.

P/E uses positive eligible common EPS and a reviewed normalized comparable multiple.
DDM and Gordon require recurring actual dividends, explicit next-payment dates and
Ke > growth. DDM discounts five dated annual dividends plus terminal value; Gordon
uses the same evidence family and payment timing. They are correlated cross-checks.
Asset-based value uses reviewed adjusted equity and eligible diluted shares, not
a P/B shortcut. Currency/scope/accounting/restatement and as-of gates apply.

Each method returns its own status, reasons, conditional estimate, source fact IDs,
assumption IDs, dates, version and sensitivity. DCF sensitivities cover discount,
terminal growth and operating margin; other methods use their own rate/multiple/
asset assumptions. There is no forced average, composite BUY score or quote gap
without a verified fresh company quote. Upside/downside must have explicitly
registered scenario assumptions; overrides inherit base versions transparently.

Data requirements / release boundary
-----------------------------------
F03 ingestion supports diluted_shares (shares), operating_nwc, restricted_cash and
lease_debt (currency, instant balances), and dividend_per_share (currency/share,
nonadditive). Populate these from reviewed reports before enabling relevant models.
The scenario editor saves versions and exposes an explicit review action to admins.
Empty inputs are not seeded with demo finance or assumed zero balances.

No real filings, forecast evidence, peer universe or current company quotes were
provided during this implementation. Default method estimates therefore remain
WITHHELD until the reviewed-data gates pass. Deterministic tests do not certify
source accuracy or investment performance. Production review from F01 still applies.

Validation: ten F04 calculation/API tests, twelve F03 financial regression tests,
and all six focused F01–F04 browser tests pass. Final F04 browser rerun and frontend
build also pass, with the existing bundle-size warning. Broader historical UI
regression gaps recorded in F01 remain outside these focused suites.
