$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
foreach ($tool in 'tailscale','caddy','npm.cmd') { Get-Command $tool -ErrorAction Stop | Out-Null }
$python = (Resolve-Path '.venv\Scripts\python.exe').Path
if (!(Test-Path 'backend\accounts.sqlite3')) { throw 'Run from the PASION installation containing your existing accounts database.' }
if (Get-NetTCPConnection -State Listen -LocalPort 8000,18180,18181 -ErrorAction SilentlyContinue) { throw 'Stop local PASION first. Ports 8000, 18180 and 18181 must be free.' }
$status = tailscale status --json | ConvertFrom-Json
if ($status.BackendState -ne 'Running') { throw 'Sign in to Tailscale on this computer first.' }
$env:PASION_DOMAIN = $status.Self.DNSName.TrimEnd('.')
if ($env:PASION_DOMAIN -notmatch '^[a-z0-9-]+\.[a-z0-9.-]+\.ts\.net$') { throw 'Missing Tailscale HTTPS hostname.' }
if (!$env:PASION_ADMIN_EMAIL) { $env:PASION_ADMIN_EMAIL = Read-Host 'Existing owner account email' }
$env:PASION_ENV = 'production'
$env:PASION_PORT = '18181'
& $python -c "import sqlite3,os,sys; db=sqlite3.connect('file:backend/accounts.sqlite3?mode=ro',uri=True); sys.exit(0 if db.execute('SELECT 1 FROM accounts WHERE lower(email)=lower(?) AND disabled=0',(os.environ['PASION_ADMIN_EMAIL'],)).fetchone() else 1)"
if ($LASTEXITCODE) { throw 'Choose the email of your existing active owner account.' }
& npm.cmd ci
if ($LASTEXITCODE) { throw 'npm ci failed.' }
& npm.cmd run build
if ($LASTEXITCODE) { throw 'Frontend build failed.' }
$config = Get-Content deploy/Caddyfile -Raw
$config = $config.Replace('{$PASION_DOMAIN} {','http://127.0.0.1:18180 {' + [Environment]::NewLine + '    bind 127.0.0.1').Replace('127.0.0.1:8000','127.0.0.1:18181').Replace('/srv/pasion/deploy','./deploy').Replace('/srv/pasion/dist','./dist')
$config = [regex]::Replace($config, '(?m)reverse_proxy 127\.0\.0\.1:18181\r? "reverse_proxy 127.0.0.1:18181 {" + [Environment]::NewLine + "            header_up Host $env:PASION_DOMAIN" + [Environment]::NewLine + '        }')
$configFile = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($configFile, "{"+[Environment]::NewLine+"admin off"+[Environment]::NewLine+"auto_https off"+[Environment]::NewLine+"}"+[Environment]::NewLine+$config)
    & caddy validate --adapter caddyfile --config $configFile
    if ($LASTEXITCODE) { throw 'Proxy configuration failed validation.' }
    $api = Start-Process $python -ArgumentList 'backend/server.py' -NoNewWindow -PassThru
    $proxy = Start-Process caddy -ArgumentList ('run --adapter caddyfile --config "'+$configFile+'"') -NoNewWindow -PassThru
    $ready = $false
    for ($i=0; $i -lt 30; $i++) {
        if ($api.HasExited -or $proxy.HasExited) { throw 'Backend or proxy stopped.' }
        try {
            $session = Invoke-RestMethod 'http://127.0.0.1:18180/api/session'
            $ready = $session.authenticated -eq $false
        } catch {}
        if ($ready) { break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Backend did not become ready.' }
    foreach ($path in '/', '/index.html') {
        $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:18180$path")
        $request.AllowAutoRedirect = $false
        $request.Proxy = $null
        $response = $request.GetResponse()
        try {
            $code = [int]$response.StatusCode
            $location = $response.Headers['Location']
            if ($code -ne 303 -or $location -ne '/access') {
                throw "Guest request to $path returned HTTP $code with Location '$location'. Expected 303 to /access."
            }
        } finally { $response.Close() }
    }
    $login = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:18180/access'
    if ($login.Content -notmatch '/api/login') { throw 'PASION sign-in page unavailable.' }
    Write-Host "PASION_DOMAIN=$env:PASION_DOMAIN"
    Write-Host 'Keep this window open. Ctrl+C stops public access.'
    & tailscale funnel 18180
    if ($LASTEXITCODE) { throw 'Funnel stopped. Check the Tailscale message above.' }
} finally {
    foreach ($process in @($proxy,$api)) { if ($process -and !$process.HasExited) { $process.Kill(); $process.WaitForExit() } }
    Remove-Item -LiteralPath $configFile -ErrorAction SilentlyContinue
}
, "reverse_proxy 127.0.0.1:18181 {" + [Environment]::NewLine + "            header_up Host $env:PASION_DOMAIN" + [Environment]::NewLine + '        }')
$configFile = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($configFile, "{"+[Environment]::NewLine+"admin off"+[Environment]::NewLine+"auto_https off"+[Environment]::NewLine+"}"+[Environment]::NewLine+$config)
    & caddy validate --adapter caddyfile --config $configFile
    if ($LASTEXITCODE) { throw 'Proxy configuration failed validation.' }
    $api = Start-Process $python -ArgumentList 'backend/server.py' -NoNewWindow -PassThru
    $proxy = Start-Process caddy -ArgumentList ('run --adapter caddyfile --config "'+$configFile+'"') -NoNewWindow -PassThru
    $ready = $false
    for ($i=0; $i -lt 30; $i++) {
        if ($api.HasExited -or $proxy.HasExited) { throw 'Backend or proxy stopped.' }
        try {
            $session = Invoke-RestMethod 'http://127.0.0.1:18180/api/session'
            $ready = $session.authenticated -eq $false
        } catch {}
        if ($ready) { break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Backend did not become ready.' }
    $gate = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:18180/'
    if ($gate.BaseResponse.ResponseUri.AbsolutePath -ne '/access') { throw 'Private workspace gate did not redirect to /access.' }
    Write-Host "PASION_DOMAIN=$env:PASION_DOMAIN"
    Write-Host 'Keep this window open. Ctrl+C stops public access.'
    & tailscale funnel 18180
    if ($LASTEXITCODE) { throw 'Funnel stopped. Check the Tailscale message above.' }
} finally {
    foreach ($process in @($proxy,$api)) { if ($process -and !$process.HasExited) { $process.Kill(); $process.WaitForExit() } }
    Remove-Item -LiteralPath $configFile -ErrorAction SilentlyContinue
}
