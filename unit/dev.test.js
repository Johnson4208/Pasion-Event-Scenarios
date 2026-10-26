import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import path from 'node:path';

const launcher = readFileSync(new URL('../scripts/dev.mjs', import.meta.url));
const windows = process.platform === 'win32';

function project(t, {vite = true} = {}) {
  const root = mkdtempSync(path.join(tmpdir(), 'pasion-dev-test-'));
  mkdirSync(path.join(root, 'scripts'));
  mkdirSync(path.join(root, 'backend'));
  writeFileSync(path.join(root, 'package.json'), '{"type":"module"}');
  writeFileSync(path.join(root, 'scripts/dev.mjs'), launcher);
  writeFileSync(path.join(root, 'backend/server.py'), '# Synthetic fixture, never real application data.');
  if (vite) {
    mkdirSync(path.join(root, 'node_modules/vite/bin'), {recursive: true});
    writeFileSync(path.join(root, 'node_modules/vite/package.json'), '{"type":"module"}');
    writeFileSync(path.join(root, 'node_modules/vite/bin/vite.js'), `
      import {writeFileSync} from 'node:fs';
      writeFileSync('frontend-started.json', JSON.stringify({pid:process.pid}));
      setInterval(() => {}, 1000);
    `);
  }
  t.after(() => {
    for (const name of ['backend-started.json', 'frontend-started.json']) {
      try {
        const {pid} = JSON.parse(readFileSync(path.join(root, name), 'utf8'));
        if (Number.isInteger(pid) && pid !== process.pid) process.kill(pid, 'SIGKILL');
      } catch {}
    }
    rmSync(root, {recursive: true, force: true});
  });
  return root;
}

function pythonPath(root) {
  return path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
}

function run(root) {
  const result = spawnSync(process.execPath, ['scripts/dev.mjs'], {
    cwd: root, encoding: 'utf8', timeout: 12000,
    env: {...process.env, PASION_EVENT_AGENT_ENABLED: '0'},
  });
  assert.ifError(result.error);
  return result;
}

function noServers(root) {
  assert.equal(existsSync(path.join(root, 'backend-started.json')), false);
  assert.equal(existsSync(path.join(root, 'frontend-started.json')), false);
}

// POSIX executable fixtures let the launcher exercise its real child processes
// without relying on an installed Python or opening any application database.
function fakePython(root, {version = [3, 12], exitCode = 7, hangProbe = false} = {}) {
  const executable = pythonPath(root);
  mkdirSync(path.dirname(executable), {recursive: true});
  const script = path.join(root, 'python-fixture.cjs');
  writeFileSync(script, `
    const fs = require('node:fs');
    if (process.argv.includes('-c')) {
      fs.writeFileSync('python-probed', 'standard-library probe');
      if (${hangProbe}) {
        process.on('SIGTERM', () => {});
        setInterval(() => {}, 1000);
      } else console.log(${JSON.stringify(JSON.stringify(version))});
    } else {
      fs.writeFileSync('backend-started.json', JSON.stringify({pid:process.pid}));
      const deadline = Date.now() + 5000;
      const timer = setInterval(() => {
        if (fs.existsSync('frontend-started.json')) {
          clearInterval(timer);
          process.exit(${exitCode});
        } else if (Date.now() > deadline) process.exit(99);
      }, 20);
    }
  `);
  const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  writeFileSync(executable, `#!/bin/sh\nexec ${quote(process.execPath)} ${quote(script)} "$@"\n`, {mode: 0o755});
}

test('missing frontend installation fails before starting either server', t => {
  const root = project(t, {vite: false});
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /npm\.cmd ci/);
  noServers(root);
});

test('missing virtual environment gives repair commands without starting servers', t => {
  const root = project(t);
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Python 3\.10 or newer/);
  assert.match(result.stderr, /-m venv \.venv/);
  noServers(root);
});

test('an existing unusable Python executable is rejected before starting servers', t => {
  const root = project(t), executable = pythonPath(root);
  mkdirSync(path.dirname(executable), {recursive: true});
  writeFileSync(executable, 'BROKEN_PASION_PYTHON_EXECUTABLE', {mode: 0o755});
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /copied or moved \.venv/);
  noServers(root);
});

test('interrupted recovery is rejected before any environment probe or server', t => {
  const root = project(t);
  if (!windows) fakePython(root);
  writeFileSync(path.join(root, 'RECOVERY-INCOMPLETE.txt'), 'Synthetic interrupted recovery');
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Recovery is incomplete/);
  assert.equal(existsSync(path.join(root, 'python-probed')), false);
  noServers(root);
});

test('an older Python fails preflight before starting servers', {skip: windows}, t => {
  const root = project(t);
  fakePython(root, {version: [3, 9]});
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Python 3\.10 or newer/);
  assert.equal(existsSync(path.join(root, 'python-probed')), true);
  noServers(root);
});

test('a Python probe that never returns is terminated before servers start', {skip: windows}, t => {
  const root = project(t);
  fakePython(root, {hangProbe: true});
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Python 3\.10 or newer/);
  noServers(root);
});

test('a backend failure stops its frontend peer and retains the failure code', {skip: windows}, t => {
  const root = project(t);
  fakePython(root, {exitCode: 7});
  const result = run(root);
  assert.equal(result.status, 7);
  assert.match(result.stderr, /Backend stopped \(exit 7\)/);
  assert.equal(existsSync(path.join(root, 'backend-started.json')), true);
  const {pid} = JSON.parse(readFileSync(path.join(root, 'frontend-started.json'), 'utf8'));
  assert.throws(() => process.kill(pid, 0), {code: 'ESRCH'});
});
