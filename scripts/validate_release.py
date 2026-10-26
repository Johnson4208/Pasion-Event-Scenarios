"""Run local acceptance and archive immutable A17 evidence, never promote.

Use the project venv Python. --browser includes bounded browser acceptance.
Reports are local audit artifacts, not externally signed certification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import release_governance as governance
from release_packages import PACKAGES

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser',action='store_true')
    scope=parser.add_mutually_exclusive_group();scope.add_argument('--focused',action='store_true');scope.add_argument('--package',choices=sorted(PACKAGES));args=parser.parse_args()
    if args.package and not PACKAGES[args.package]['tests']:parser.error('Deferred package has no releasable acceptance suite')
    identifier=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(6)
    target=ROOT/'artifacts'/'release-validation'/identifier;target.mkdir(parents=True,exist_ok=False)
    npm='npm.cmd' if os.name=='nt' else 'npm'
    suites=[('backend',[sys.executable,'-m','unittest','discover','-s','backend'],600),
            ('frontend_unit',[npm,'run','test:unit'],120),('frontend_build',[npm,'run','build'],180)]
    if args.focused:
        suites[0]=('backend_governance',[sys.executable,'-m','unittest','discover','-s','backend','-p','test_release_governance.py'],120)
    if args.package:
        suites=[(Path(name).stem,[sys.executable,'-m','unittest','discover','-s','backend','-p',name],180) for name in PACKAGES[args.package]['tests']]+suites[1:]
    if args.browser:suites.append(('browser',[npm,'run','test:ui','--','tests/f01.spec.js','tests/f03.spec.js','tests/f07.spec.js','tests/f08.spec.js','tests/f15.spec.js','tests/f16.spec.js','--global-timeout=180000'],210))
    before=governance.fingerprint(ROOT);results=[]
    for name,command,timeout in suites:
        print('Validating '+name,flush=True)
        with (target/(name+'.log')).open('w',encoding='utf-8') as log:
            try:
                result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
                code=result.returncode;status='PASS' if code==0 else 'FAIL'
            except subprocess.TimeoutExpired:code=None;status='TIMEOUT'
            except OSError:code=None;status='UNAVAILABLE'
        results.append(dict(suite=name,status=status,exit_code=code,log_file=name+'.log',
                            log_sha256=hashlib.sha256((target/(name+'.log')).read_bytes()).hexdigest(),
                            evidence_kind='LOCAL_FIXTURES_OR_MOCKS_NOT_REAL_PROVIDER_CERTIFICATION'))
    after=governance.fingerprint(ROOT)
    report=dict(run_id=identifier,checked_at=datetime.now(timezone.utc).isoformat(),code_sha256=before,
                reproducible_code_unchanged=before==after,suites=results,
                browser_status='INCLUDED' if args.browser else 'NOT_RUN',backend_scope=args.package or ('GOVERNANCE_ONLY' if args.focused else 'COMPLETE'),
                dependency_suites_included=False if args.package else None,
                release_manifest=governance.manifest(ROOT),policy='LOCAL_VALIDATION_NOT_PRODUCTION_CERTIFICATION')
    with (target/'manifest.json').open('x',encoding='utf-8') as output:json.dump(report,output,indent=2)
    print('Audit manifest: '+(target/'manifest.json').relative_to(ROOT).as_posix(),flush=True)
    return 0 if before==after and all(r['status']=='PASS' for r in results) else 1

if __name__=='__main__':sys.exit(main())
