# F11 — Company News and research monitoring

Native Company News now defaults to reviewed evidence, with existing layout selection, topic/company filters, source article links, company links and private server bookmarks. Bundled stories/images and their browser bookmarks remain in explicit Illustrative sample stories mode. There are no registered real feeds or supplied reviewed articles, so default coverage starts UNAVAILABLE.

## Admission and source discipline

Admin POST `/api/admin/news/sources` registers immutable `id, name, source_url` (public HTTPS), `permission_basis, coverage, max_gap_seconds` (60–2592000), `permitted:true`. The administrator must establish RSS/provider/filing permission and appropriate coverage before registration. This is an explicit admission assertion, not automatic verification of licensing or completeness. No external crawler, RSS polling schedule, credentials or live provider integration was invented.

Admin POST `/api/admin/news/ingest` accepts `source_id, url, title, summary, category, tickers, revision, published_at, ingested_at, claims` and optional `cluster_key`. Source URL host must match the registered host. Clocks require offsets; publication and ingestion cannot be future, and ingestion cannot precede publication. Each claim requires short `text, excerpt, locator` (max 200 characters each). The administrator supplies extracted factual claims after reviewing the original content; this version has no automatic NLP extractor or fabricated source excerpts. known_at is at least actual server acceptance time. Every article revision is immutable and has new claim IDs.

Canonical URL identity strips fragments and common tracking parameters (utm_, gclid, fbclid), normalizes query order and ignores a terminal slash. Duplicate URL/revision admission is rejected. Normalized headline plus publication day is the default duplicate cluster. Optional reviewed cluster_key groups reworded/syndicated stories. This thin heuristic is not universal semantic deduplication; editors must curate rewritten syndication and inspect source independence. Cluster stories are collapsed in the newsroom and cannot support one another during claim review. Different domains do not automatically make evidence independent or true.

## Claim graph and historical reads

Admin POST `/api/admin/news/review` requires `article_id, claim_id, relations, review_note`. Each relation requires another `article_id, claim_id, stance` (SUPPORTING/REFUTING), `explanation`. An article, same canonical identity, duplicate cluster or duplicate relation cannot corroborate itself. Relation snapshots include excerpt, source URL/provider and publication/ingestion/known/revision clocks. The endpoint is explicit human claim review; reviewers must check context, factual applicability and independence, including filings and consequential economic claims.

Review status is SUPPORTED for supporting relations only, REFUTED for refuting relations only, CONFLICTING for both and INSUFFICIENT with none. These are human-reviewed relation labels, not a probability of truth, a provider/domain trust score or a market return signal. Each review appends an immutable version. Ambiguous same-time reviews or article revisions are insufficient. If a corroborating source is revised, its old relationship cannot sustain a current supported label until renewed review.

Member GET `/api/research/news?origin=<offset clock>` returns the latest article revision known at origin, claim evidence/status, source permission/coverage declarations, accepted arrival gaps and mean ingestion latency. Future origins are rejected. Later revisions/reviews cannot enter earlier research origins. Source GAP is visible when no accepted arrivals exist or the declared maximum gap is exceeded. READY means recent accepted arrival, not complete provider coverage. The response remains PARTIAL when articles exist; no total-market coverage claim is made. Latest accepted articles are capped at 200 per response.

Member POST `/api/research/news/bookmarks` takes `article_id, saved` (boolean) and ignores supplied owner fields. Original bookmarked revisions remain available and visibly superseded when newer articles arrive; bookmarks never silently migrate to rewritten claims. Read and bookmark storage are private even from other admins via member endpoints.

## Explicit driver review

Member POST `/api/research/news/proposals` requires `article_id, claim_id, ticker, driver, proposed_change, rationale`. Only a currently supported claim and a ticker explicitly associated with the article may create a private PENDING_RESEARCH_REVIEW proposal. The source claim/review is snapshotted. Member GET `/api/research/news/proposals` returns only own proposals and review decisions.

The submission explicitly shares that proposal's economic content with the admin review queue. Admin GET `/api/admin/news/proposals` returns submitted proposal content, with no account identity, private bookmarks, credentials or portfolio data. Admin POST `/api/admin/news/decide` requires `proposal_id, decision` (APPROVED_FOR_DRIVER_REVIEW/REJECTED), `note`. Approval checks current claim support again; contradictory, revised or missing evidence blocks approval. Decisions append to the archive. An admin News research review tab exposes this queue and decision form.

Approval permits separate F04 forecast-driver review. F11 never updates financial facts, historical EPS, valuation assumptions, valuation runs, Stock Analytics or Kelly. No raw news claim can bypass F03/F04 eligibility/evidence gates. driver/proposed_change are proposals, not validated finance-registry driver definitions. No automated financial assumption changes are implemented.

SQLite accounts storage tables: news_sources, news_articles, news_reviews, owner-FK news_bookmarks/news_proposals and news_decisions. Server policies protect all admin admission/review endpoints; member APIs require authentication and resolve ownership from the session. F01 production identity/storage review remains necessary.

## Validation

Core/API tests cover permitted host admission, future clocks, feed gaps, vintage isolation, URL tracking duplicates and headline clusters, supported/refuted/conflicting/insufficient review states, historical review cutoffs, private bookmarks/proposals, revised corroboration, preserved bookmarked revisions and approval gates. Browser tests exercise empty coverage, explicit samples, cluster collapse, source/claim drawer, bookmarks and proposed driver review. No fixture certifies a real provider's coverage or an article's truth.

Validation completed: all 166 backend regression tests passed. After final chronology/clustering and decision-status updates, all 8 focused F11 backend/API tests passed. All 3 F11 browser checks passed, including the administrator decision flow; adjacent F01/F10 browser checks also passed. Production build passed with the existing large-bundle warning. Local frontend/backend were restarted with F11 active. Broader historical browser-suite gaps remain documented in F01. No actual RSS/provider dataset was installed or certified.
