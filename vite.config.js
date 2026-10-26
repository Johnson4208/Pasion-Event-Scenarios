import { defineConfig } from 'vite';

// Vite's fs.deny does not cover its public-directory middleware. Apply the
// same private-file boundary before static serving, including preview.
function blockPrivateFiles(request, response, next) {
  let pathname = (request.url || '/').split('?')[0];
  try {
    pathname = decodeURIComponent(pathname).replaceAll('\\', '/');
  } catch {
    response.writeHead(400).end('Invalid request path.');
    return;
  }
  const privateDirectory = /(?:^|\/)(?:backend|\.venv|\.git|event-agent-state|private-event-models)(?:\/|$)/i;
  const privateFile = /(?:^|\/)(?:\.env[^/]*|recovery-manifest\.json|RECOVERY-INCOMPLETE\.txt)$|\.(?:sqlite\d*|db)[^/]*$|\.(?:crt|pem)$/i;
  if (privateDirectory.test(pathname) || privateFile.test(pathname)) {
    response.writeHead(403, {'Content-Type':'text/plain; charset=utf-8', 'Cache-Control':'no-store'});
    response.end('Private project files are not served.');
    return;
  }
  next();
}

export default defineConfig({
  plugins: [{
    name: 'pasion-private-files',
    configureServer(server) { server.middlewares.use(blockPrivateFiles); },
    configurePreviewServer(server) { server.middlewares.use(blockPrivateFiles); },
  }],
  server: {
    strictPort: true,
    allowedHosts: [
      'cheque-echo-handle-cognitive.trycloudflare.com',
      'stud-optimization-magnitude-relation.trycloudflare.com',
      'berry-infections-aged-prisoners.trycloudflare.com',
    ],
    proxy: {'/api': 'http://127.0.0.1:8000'},
    fs: {
      deny: [
        '.env', '.env.*', '*.{crt,pem}', '**/.git/**', '**/backend/**', '**/.venv/**',
        '**/event-agent-state/**', '**/private-event-models/**',
        '**/*.{sqlite,sqlite3,db}*', '**/recovery-manifest.json', '**/RECOVERY-INCOMPLETE.txt',
      ],
    },
  },
});
