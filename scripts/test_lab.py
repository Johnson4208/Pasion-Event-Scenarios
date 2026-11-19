"""Run the project's test suites in a disposable tracked-source checkout."""
import argparse,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--ui',action='store_true',help='Include all Playwright tests; installs Chromium first');a=parser.parse_args()
 root=Path(__file__).resolve().parents[1];npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
 if not npm:parser.error('Install Node.js/npm first')
 try:tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
 except (OSError,subprocess.CalledProcessError):parser.error('Run from a GitHub Desktop checkout with Git installed')
 if 'backend/server.py' not in tracked:parser.error('Incomplete Git checkout')
 output=root/'artifacts'/'test-lab';output.mkdir(parents=True,exist_ok=True)
 results=[]
 with tempfile.TemporaryDirectory(prefix='pasion-full-test-lab-') as tmp:
  target=Path(tmp)
  for relative in filter(None,tracked):
   source=root/relative
   # Runtime state and credentials never belong in the disposable lab.
   if source.is_symlink() or any(part in ('.venv','node_modules','private-financial-sources','uploads') for part in Path(relative).parts) or source.suffix in ('.sqlite3','.db') or source.name.startswith('.env'):continue
   if source.is_file():
    dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
  env={k:v for k,v in os.environ.items() if not k.startswith(('PASION_','SOLVAI_'))}
  env.update(PASION_ENV='test',PASION_EVENT_AGENT_ENABLED='0',PYTHONUTF8='1',PASION_SEC_USER_AGENT='')
  def run(name,args):
   start=time.perf_counter()
   with (output/(name+'.log')).open('w',encoding='utf-8') as log:
    try:r=subprocess.run(args,cwd=target,env=env,stdout=log,stderr=subprocess.STDOUT);code=r.returncode
    except OSError as e:log.write(str(e));code=127
   results.append(dict(suite=name,exit_code=code,seconds=round(time.perf_counter()-start,2)))
   print(name+': '+('PASS' if code==0 else 'FAIL (see artifacts/test-lab/'+name+'.log)'),flush=True)
   return code==0
  run('backend',[sys.executable,'-m','unittest','discover','-s','backend','-p','test_*.py'])
  run('distribution-simulation',[sys.executable,'testing/simulate_distribution.py','--output',str(output/'distribution.json')])
  if run('npm-install',[npm,'ci']):
   run('unit',[npm,'run','test:unit']);run('build',[npm,'run','build'])
   if a.ui and run('browser-install',[npm,'exec','--','playwright','install','--with-deps','chromium']):
    # Never attach tests to the user's already-running frontend.
    config=target/'playwright.config.js'
    config.write_text(config.read_text(encoding='utf-8').replace('reuseExistingServer:true','reuseExistingServer:false'),encoding='utf-8')
    run('ui',[npm,'run','test:ui'])
    for folder in ('test-results','playwright-report','artifacts'):
     if (target/folder).is_dir():shutil.copytree(target/folder,output/folder,dirs_exist_ok=True)
  else:
   results.append(dict(suite='frontend-checks',exit_code=1,reason='npm ci failed'))
 report=dict(mode='ISOLATED_TRACKED_SOURCE_COPY',ui_requested=a.ui,results=results,passed=all(r['exit_code']==0 for r in results))
 (output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
