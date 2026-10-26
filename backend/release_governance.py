"""A17 evidence-based release gates; test success alone is not certification."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import finance_core
import release_packages

VERSION = 'a17-v1'
LADDER = ('SAMPLE','REVIEW_ONLY','RESEARCH_READY','SHADOW_VALIDATED','EXECUTION_ELIGIBLE')
BASE_GATES = ('contract','source','temporal','security','feature_checks','version_reproducibility','provider_stability')
FEATURES = {
    'financial_research': ('accounting_identities','revision_timing','fiscal_periods'),
    'valuation': ('driver_lineage','sector_eligibility','sensitivity'),
    'market_models': ('nested_walk_forward','frozen_champion','future_cohort','calibration_drift','untouched_holdout'),
    'trade_feasibility': ('lot_cash_holdings','gap_outcomes','fx','corporate_actions'),
    'portfolio': ('owner_isolation','cashflow_reconciliation','corporate_actions','fx'),
    'distribution': ('concurrent_reserve_retry','capacity_reconciliation','verified_tape','exposure_policy'),
}

def fingerprint(root):
    """Deterministic code identity, excluding runtime data and secrets."""
    digest=hashlib.sha256()
    root=Path(root)
    paths=[]
    for folder, suffixes in [('backend', {'.py'}),('src',{'.js','.jsx','.ts','.scss'}),('scripts',{'.py','.ps1','.mjs'}),('unit',{'.js'}),('tests',{'.js'})]:
        paths.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    paths.extend(p for p in (root/'package.json',root/'package-lock.json',root/'vite.config.js',root/'playwright.config.js') if p.exists())
    for path in sorted(paths,key=lambda p:p.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode());digest.update(b'\0');digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()

def evaluate(feature, evidence=None, now=None):
    if feature not in FEATURES:raise ValueError('Unknown release feature')
    now=now or datetime.now(timezone.utc);evidence=evidence or {}
    reasons=[];checks={}
    # Every gate needs a current report, lineage and an accountable release
    # owner. A historical summary or boolean passed flag cannot promote.
    for gate in BASE_GATES + FEATURES[feature]:
        item=evidence.get(gate,{})
        valid=False
        try:
            valid=(item.get('status')=='PASS' and bool(item.get('report_id')) and
                   bool(item.get('source_ids')) and bool(item.get('release_owner')) and bool(item.get('calculation_version')) and bool(item.get('snapshot_id')) and
                   finance_core.instant(item['known_at'])<=now<finance_core.instant(item['expires_at']))
        except (ValueError,TypeError,KeyError):pass
        checks[gate]='PASS' if valid else 'WITHHELD'
        if not valid:reasons.append(gate.upper()+'_EVIDENCE_MISSING_FAILED_OR_STALE')
    stage='REVIEW_ONLY' if reasons else 'RESEARCH_READY'
    # Shadow validation is separate from economic research. Execution has no
    # supported promotion path in this release, even with all research gates.
    if stage=='RESEARCH_READY' and feature=='distribution':
        stage='SHADOW_VALIDATED'
    return dict(feature=feature,status=stage,release_ready=not reasons,checks=checks,
                reason_codes=reasons,execution_eligible=False,allocation_weight=None,
                rollback_triggers=['SOURCE_STALE_OR_REVISED','CONTRACT_OR_SECURITY_FAILURE','VERSION_MISMATCH','MODEL_DRIFT_OR_EXPIRED','RECONCILIATION_REQUIRED'])

def manifest(root, now=None):
    now=now or datetime.now(timezone.utc)
    # No manual gate reports have been admitted by a governed review workflow.
    # CI/local test output is audit evidence only, not a release-owner signature.
    features=[evaluate(name,now=now) for name in FEATURES]
    return dict(version=1,governance_version=VERSION,checked_at=now.isoformat(),
                status='REVIEW_ONLY',packages=release_packages.roadmap(),status_ladder=list(LADDER),features=features,
                execution_eligible=False,live_routing=False,
                evidence_admission='NOT_CONFIGURED_NO_AUTOMATIC_PROMOTION',
                policy='INDEPENDENT_FEATURE_GATES_WITH_EXPLICIT_ABSTENTION')
