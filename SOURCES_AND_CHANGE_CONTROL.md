# Supplied sources, limitations and change control

This implementation record uses screenshots and text supplied in this chat plus
local Pasion code inspected in this checkout. The bibliography below is copied
as a user-supplied reference list. The original PDFs and archives were not
independently inspected during this implementation; their page counts, dates
and claims are not independently verified here.

| Ref | Supplied reference | Role asserted by supplied blueprint |
| --- | --- | --- |
| P0 | `pasion2.0-main(1).zip` | Pasion baseline archive; described as inspected 12 Oct 2026 |
| L0 | `SolvAI58(1).zip`, `SolvAI58/SolvAI56.2-Research-Clarity` | Older source baseline, not the later documented 58.1 snapshot |
| S1 | `SolvAI58_Master_Thuat_Toan_Du_Lieu_Lo_Trinh_Prompt_VI.pdf` | 28 pages; 7 Oct 2026; canonical contracts, roadmap and R01–R23 |
| S2 | `SolvAI58.1_Cau_truc_Thuat_toan_va_Lo_trinh_VI.pdf` | 36 pages; 3 Oct 2026; historical 58.1 source review |
| S3 | `SolvAI58_1_Nghien_cuu_Nang_cap_Chung_khoan_VI.pdf` | 39 pages; 4 Oct 2026; target design and proposed experiments |

No live market provider, external broker, external user account or historical
investment performance has been independently certified. A later design PDF
does not establish that the older archive contains that code, nor that those
historical tests were rerun against Pasion. Local mocked fixtures and manually
reviewed sources are explicitly separate from real-provider integration.

The current implementation contains guarded finance and shadow primitives,
but their presence does not mean all data, production operations or release
gates are ready. A score, valuation gap or market pattern does not authorize
investment advice or trade execution. Quantitative hedging/capacity estimates
remain gated on venue, instrument, account and market evidence. No live routing
or verified investment-performance claim follows from deterministic tests.

Changes should extend the economic core first and link reusable algorithms to
existing screens. Preserve navigation, language/preferences, styling, saved
layouts and original document routes. Use `IMPLEMENTATION_ROADMAP.md` and the
package registry for dependencies and outstanding work. Each change record
must distinguish proposed, implemented, guarded and withheld capabilities,
identify the code/test scope, and retain immutable local run IDs and source
hashes. Historical references cannot replace current acceptance evidence.

Existing `backend/F*_RELEASE.md` and `backend/A*_RELEASE.md` describe individual
changes and limitations. Release artifacts under `artifacts/release-validation/`
record local suite outcomes; they are not signed external attestations and do
not promote the live REVIEW_ONLY manifest. Broker/legal/operational expansion
requires a separate release decision and evidence.
