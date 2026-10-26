"""Dependency roadmap and executable local suite ownership, not release approval."""
PACKAGES = {
    'P0.0': dict(name='Baseline and security',dependencies=[],tests=['test_security.py','test_document_api.py','test_operational_health.py'],remaining=['COMPLETE_BROWSER_REGRESSION','PRODUCTION_IDENTITY_AND_STORAGE_REVIEW']),
    'P0.1': dict(name='Canonical data, provenance and time',dependencies=['P0.0'],tests=['test_contracts.py','test_information_periods.py','test_report_review.py','test_finance_core.py'],remaining=['GOVERNED_REAL_SOURCE_ADMISSION']),
    'P0.2': dict(name='Economic metrics',dependencies=['P0.1'],tests=['test_profitability.py','test_quality.py'],remaining=['REVIEWED_PEER_REGISTRY','COMPLETE_ANOMALY_INPUT_COVERAGE']),
    'P0.3': dict(name='Shared feasibility',dependencies=['P0.1'],tests=['test_feasibility.py','test_feasibility_api.py','test_a10.py'],remaining=['VERIFIED_FX_AND_CORPORATE_ACTION_POLICY']),
    'P1.0': dict(name='Economic screens',dependencies=['P0.2','P0.3'],tests=['test_finance_api.py','test_valuation_api.py','test_finance_ingestion.py'],remaining=['COMPLETE_SOURCE_DRAWER_AND_DOCUMENT_REVIEW_BROWSER_ACCEPTANCE']),
    'P1.1': dict(name='Operating forecast and valuation',dependencies=['P1.0'],tests=['test_forecast.py','test_valuation.py','test_valuation_gap.py'],remaining=['VERIFIED_ISSUER_DRIVERS_AND_SECTOR_SIGNOFF']),
    'P1.2': dict(name='Manual portfolio and risk',dependencies=['P0.3'],tests=['test_portfolio_ledger.py','test_portfolio_api.py','test_a11.py'],remaining=['RECONCILED_EVENT_FX_AND_CORPORATE_ACTION_HISTORY','ACTUAL_RETURN_ACCEPTANCE']),
    'P2.0': dict(name='Selective optional research',dependencies=['P1.0'],tests=['test_market_summary.py','test_technical.py','test_stock_models.py','test_macro_evidence.py','test_event_research.py','test_news_evidence.py','test_watch_events.py','test_analytic_assistant.py'],remaining=['PER_FEATURE_PROVIDER_COVERAGE','NESTED_MODEL_VALIDATION_AND_FUTURE_COHORT']),
    'P3.0': dict(name='Distribution shadow',dependencies=['P0.3','P1.1','P1.2'],tests=['test_a14.py','test_a15.py','test_distribution_shadow.py'],remaining=['VERIFIED_EXPOSURE_POLICY','SAME_WINDOW_TAPE_CERTIFICATION','OPERATIONAL_RECONCILIATION']),
    'P4+': dict(name='Live execution and expansion',dependencies=['P3.0'],tests=[],remaining=['SEPARATE_OPERATIONAL_LEGAL_BROKER_RELEASE','SHARED_MULTI_HOST_COORDINATOR','MARGIN_BORROW_AND_EXECUTION_RISK']),
}

def roadmap():
    return [dict(stage=stage,**record,status='DEFERRED' if stage=='P4+' else 'GUARDED',
                 exit_gate='NOT_CERTIFIED',dependency_tests_included=False) for stage,record in PACKAGES.items()]
