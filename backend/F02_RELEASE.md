F02 market evidence snapshots
============================

GET /api/market/summary?mode=demo|provider requires a current Pasion session.
The version-1 envelope reports dataset mode, evaluated_at, provider_status,
per-instrument origin/status/reason/source/as_of, benchmark and breadth states.
Demo is a separate immutable fixture with no fabricated quote timestamps.

The existing dashboard consumes this endpoint through useMarketSummary, refreshes
every 30 seconds, and times out requests after eight seconds. Local sample fallback
is permitted only in demo mode. Provider mode has no illustrative chart history.
Quotes include expires_at; the browser suppresses expired quotes between polls.
Existing watchlists, dashboard arrangement, macro samples and navigation remain.

No live vendor is connected by this change. Configure PASION_MARKET_SNAPSHOT to a
trusted adapter's JSON cache file on the server. Never expose this path through API
responses. The adapter must independently verify source authenticity, exchange
calendar holidays, session windows and instrument definitions; a JSON verified
flag is an adapter assertion, not independent provider certification.

Cache schema:
{"verified":true,"source":"Provider name","quotes":{"SPX":{
"price":100,"change":0,"as_of":"2026-10-13T14:59:00Z",
"session_open":"2026-10-13T13:30:00Z","session_close":"2026-10-13T20:00:00Z",
"venue":"US index","timezone":"America/New_York","calendar":"provider-calendar-v1",
"currency":"USD","unit":"Index points","max_age_seconds":300}}}

All clocks require offsets. Provider prices require finite positive values, known
units, venue/currency/calendar/timezone metadata and quote timestamps inside the
supplied session. Future quotes are WITHHELD; expired prices are STALE with null
amounts. Missing/invalid caches stay UNAVAILABLE. Coverage is restricted to the
supported instrument registry and is never represented as total market coverage.
S&P 500 is the optional benchmark when ready. Equity breadth stays unavailable
until a verified constituent-universe adapter exists; index/crypto/commodity
changes cannot stand in for consolidated market breadth or turnover.

The provider adapter and calendar integration remain release dependencies before
real-data certification. These deterministic checks do not certify live feeds.

Validation: seven Python API/quote tests and two browser tests pass. Cases include
authentication, zero change, missing provider, invalid cache, missing offsets,
future/out-of-session quotes, stale data, sample separation and in-browser expiry.
Production build passes with the existing bundle-size warning.
