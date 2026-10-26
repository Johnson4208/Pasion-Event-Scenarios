$ErrorActionPreference = 'Stop'
$pasionRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $pasionRoot
try {
    & .\.venv\Scripts\python.exe -m unittest discover -s backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend acceptance failed' }
    & npm.cmd run test:unit
    if ($LASTEXITCODE -ne 0) { throw 'Frontend unit acceptance failed' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Production build failed' }
    & npm.cmd run test:ui -- tests/f01.spec.js tests/f02.spec.js tests/f03.spec.js tests/f04.spec.js tests/f05.spec.js tests/f06.spec.js tests/f07.spec.js tests/f08.spec.js tests/f09.spec.js tests/f10.spec.js tests/f11.spec.js tests/f13.spec.js tests/f14.spec.js tests/f15.spec.js tests/f16.spec.js
    if ($LASTEXITCODE -ne 0) { throw 'Focused browser acceptance failed' }
} finally { Pop-Location }
