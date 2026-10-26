import {existsSync} from 'node:fs';
import {spawn, spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const windows = process.platform === 'win32';
const python = path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
if (existsSync(path.join(root, 'RECOVERY-INCOMPLETE.txt'))) {
  console.error('Recovery is incomplete. Do not run this folder. Run recovery again into a new folder; see BACKEND-RECOVERY.md.');
  process.exit(1);
}
if (!existsSync(path.join(root, 'node_modules/vite/bin/vite.js'))) {
  console.error('Frontend dependencies are missing. Run npm.cmd ci on Windows, or npm ci on macOS/Linux, in this project folder, then retry.');
  process.exit(1);
}
function explainPython() {
  console.error('The project Python environment is missing or cannot run Python 3.10 or newer. A copied or moved .venv may need to be re-created.');
  console.error(windows
    ? 'Create the project environment: py -3.12 -m venv .venv'
    : 'Create the project environment: python3 -m venv .venv');
  console.error(windows
    ? 'Then run: .\\.venv\\Scripts\\python.exe -m pip install -r backend/requirements-documents.txt'
    : 'Then run: .venv/bin/python -m pip install -r backend/requirements-documents.txt');
}
if (!existsSync(python)) {
  explainPython();
  process.exit(1);
}
// Check only the interpreter and standard library; never import the application
// or open its databases during preflight.
const probe = spawnSync(python, ['-I', '-c', 'import json, sqlite3, sys; print(json.dumps(list(sys.version_info[:2])))'], {
  cwd: root, encoding: 'utf8', timeout: 5000, killSignal: 'SIGKILL', maxBuffer: 64 * 1024,
  windowsHide: true,
});
let pythonVersion;
try { pythonVersion = JSON.parse(probe.stdout || ''); } catch {}
if (probe.error || probe.status !== 0 || !Array.isArray(pythonVersion) ||
    pythonVersion.length !== 2 || !pythonVersion.every(Number.isInteger) ||
    pythonVersion[0] < 3 || (pythonVersion[0] === 3 && pythonVersion[1] < 10)) {
  explainPython();
  process.exit(1);
}

const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) {
    if (!child.pid || child.exitCode !== null) continue;
    if (windows) {
      // The virtual-environment launcher has a Python child on Windows.
      spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], {stdio: 'ignore', windowsHide: true});
    } else child.kill('SIGTERM');
  }
}
function launch(label, executable, args) {
  const child = spawn(executable, args, {
    cwd: root, stdio: 'inherit', windowsHide: true,
    env: {...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1'},
  });
  children.push(child);
  child.once('error', error => { console.error(`${label}: ${error.message}`); stop(1); });
  child.once('exit', (code, signal) => {
    if (!stopping) {
      console.error(`${label} stopped${signal ? ` (${signal})` : ` (exit ${code})`}.`);
      stop(code || 1);
    }
  });
}

process.once('SIGINT', () => stop());
process.once('SIGTERM', () => stop());
launch('Backend', python, ['-X', 'utf8', 'backend/server.py']);
if (process.env.PASION_EVENT_AGENT_ENABLED === '1') launch('Event Intelligence Agent', python, ['-X', 'utf8', 'backend/event_agent.py', '--interval-minutes', process.env.PASION_EVENT_POLL_MINUTES || '30']);
launch('Frontend', process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--strictPort']);
