import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer, preview} from 'vite';
import projectConfig from '../vite.config.js';

test('the development server blocks local databases and recovery state on every file-serving route', async t => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'pasion-private-files-'));
  t.after(() => rm(root, {recursive:true, force:true}));
  // Only synthetic files are created: no application databases are opened.
  const privateFiles = [
    'backend/accounts.sqlite3', 'event-agent-state/intelligence.sqlite3',
    'event-agent-state/metadata.json', 'private-event-models/catalog.json',
    'backup.sqlite', 'backup.sqlite3-wal', 'backup.sqlite3-shm',
    'backup.sqlite3-journal', 'backup.sqlite3.bak', 'backup.db', 'backup.DB-WAL',
    '.env', '.env.local', 'recovery-manifest.json', 'RECOVERY-INCOMPLETE.txt',
  ];
  const secret = 'SYNTHETIC_PRIVATE_CONTENT_MUST_NEVER_BE_SERVED';
  for (const relative of privateFiles) {
    const file = path.join(root, relative);
    await mkdir(path.dirname(file), {recursive:true});
    await writeFile(file, secret);
  }
  await writeFile(path.join(root, 'index.html'), '<!doctype html><title>Synthetic public app</title>');
  await mkdir(path.join(root, 'public'));
  await writeFile(path.join(root, 'public', 'logo.svg'), '<svg xmlns="http://www.w3.org/2000/svg"/>');
  await writeFile(path.join(root, 'public', 'public-backup.sqlite3'), secret);
  const server = await createServer({
    ...projectConfig, configFile:false, root, logLevel:'silent',
    server:{...projectConfig.server, host:'127.0.0.1', port:0,
      fs:{...projectConfig.server.fs, allow:[root]}},
  });
  await server.listen();
  t.after(() => server.close());
  const base = 'http://127.0.0.1:'+server.httpServer.address().port;
  for (const relative of privateFiles) {
    const absolute = path.join(root, relative).replaceAll('\\','/');
    for (const route of ['/'+relative, '/'+relative+'?raw', '/@fs/'+absolute]) {
      const response = await fetch(base+route);
      assert.equal(response.status, 403, route);
      assert.ok(!(await response.text()).includes(secret), route);
    }
  }
  const publicDatabase = await fetch(base+'/public-backup.sqlite3');
  assert.equal(publicDatabase.status,403,'public directory must not bypass database protection');
  assert.ok(!(await publicDatabase.text()).includes(secret));
  for (const route of ['/', '/logo.svg']) {
    const response = await fetch(base+route);
    assert.equal(response.status,200,route+' remains accessible');
    await response.arrayBuffer();
  }
});

test('preview also blocks a private database mistakenly placed in public build files', async t => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'pasion-preview-private-'));
  t.after(() => rm(root, {recursive:true, force:true}));
  await mkdir(path.join(root, 'dist'));
  await writeFile(path.join(root, 'dist', 'index.html'), '<!doctype html><title>Public preview</title>');
  await writeFile(path.join(root, 'dist', 'backup.sqlite3'), 'SYNTHETIC_PRIVATE_BACKUP');
  const server = await preview({
    ...projectConfig, root, configFile:false, logLevel:'silent',
    preview:{host:'127.0.0.1',port:0,strictPort:true},
  });
  t.after(() => new Promise((resolve,reject) => server.httpServer.close(error => error ? reject(error) : resolve())));
  const base = 'http://127.0.0.1:'+server.httpServer.address().port;
  const denied = await fetch(base+'/backup.sqlite3');
  assert.equal(denied.status,403);
  assert.ok(!(await denied.text()).includes('SYNTHETIC_PRIVATE_BACKUP'));
  const publicPage = await fetch(base+'/');
  assert.equal(publicPage.status,200);
  await publicPage.text();
});
