# Arranca UFG Knowledge Hub con un solo comando:
#     powershell -ExecutionPolicy Bypass -File iniciar.ps1
# (o doble clic en iniciar.bat)
#
# La primera vez prepara el entorno y pide la clave de Groq (se guarda sólo en
# .env, que nunca se sube a GitHub). Las siguientes veces arranca directo.

$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$py = '.venv\Scripts\python.exe'

# 1. Entorno de Python
if (-not (Test-Path $py)) {
    Write-Host 'Creando el entorno de Python (sólo la primera vez)...' -ForegroundColor Cyan
    python -m venv .venv
}
& $py -c "import flask, waitress, chromadb" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Instalando dependencias...' -ForegroundColor Cyan
    & $py -m pip install -q -r requirements.txt
}

# 2. Configuración
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
$envText = Get-Content '.env' -Raw -Encoding UTF8

function Set-EnvValue([string]$name, [string]$value) {
    if ($script:envText -match "(?m)^$name=.*$") {
        $script:envText = $script:envText -replace "(?m)^$name=.*$", "$name=$value"
    } else {
        $script:envText += "`n$name=$value"
    }
}

if ($envText -notmatch '(?m)^GROQ_API_KEY=\S+') {
    Write-Host ''
    Write-Host 'Falta la clave gratuita de Groq (IA en la nube).' -ForegroundColor Yellow
    Write-Host '  1. Entra a https://console.groq.com/keys con tu cuenta de Google o GitHub.'
    Write-Host '  2. Pulsa "Create API Key" y copia la clave (empieza con gsk_).'
    Start-Process 'https://console.groq.com/keys'
    $clave = (Read-Host 'Pega aquí la clave de Groq').Trim()
    if ($clave -notmatch '^gsk_') {
        Write-Host 'Esa clave no parece de Groq (debe empezar con gsk_). Vuelve a ejecutar el script.' -ForegroundColor Red
        exit 1
    }
    Set-EnvValue 'GROQ_API_KEY' $clave
    Set-EnvValue 'AI_PROVIDERS' 'groq,gemini'
    Set-EnvValue 'SECURITY_AI_PROVIDERS' 'groq,gemini'
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), $envText, (New-Object Text.UTF8Encoding($false)))
    Write-Host 'Clave guardada en .env' -ForegroundColor Green
}

# 3. Comprobar la IA
Write-Host 'Comprobando la IA...' -ForegroundColor Cyan
$env:PYTHONIOENCODING = 'utf-8'
& $py manage.py ai --test 'Responde sólo: listo' 2>$null | Select-Object -Last 2

# 4. Arrancar
Start-Job { Start-Sleep 4; Start-Process 'http://127.0.0.1:5001' } | Out-Null
& $py wsgi.py
