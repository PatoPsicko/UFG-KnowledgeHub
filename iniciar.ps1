# Arranca UFG Knowledge Hub con un solo comando y muestra el link para compartir:
#     powershell -ExecutionPolicy Bypass -File iniciar.ps1
# (o doble clic en iniciar.bat)
#
#   -SinTunel    sólo esta PC y la red local, sin link público
#   -SinNavegador  no abre el navegador al final (pruebas automáticas)
#
# Link público: si Tailscale está instalado y con sesión iniciada se usa
# Tailscale Funnel, que da un link FIJO (https://tu-pc.tu-red.ts.net) y no
# cambia nunca; si no, un túnel rápido de Cloudflare (gratis, pero el link
# cambia cada vez). Ver docs/DEMO_20_USUARIOS.md.
#
# La primera vez prepara el entorno y pide la clave de Groq (se guarda sólo en
# .env, que nunca se sube a GitHub). Las siguientes veces arranca directo.
# Para apagar todo: Ctrl+C o cerrar esta ventana.

param([switch]$SinTunel, [switch]$SinNavegador)

$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$py = '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'

# 1. Entorno de Python
if (-not (Test-Path $py)) {
    Write-Host 'Creando el entorno de Python (sólo la primera vez)...' -ForegroundColor Cyan
    python -m venv .venv
}
& $py -c "import flask, waitress, chromadb, qrcode" 2>$null
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
$puerto = if ($envText -match '(?m)^APP_PORT=(\d+)') { $Matches[1] } else { '5001' }

# 3. Comprobar la IA
Write-Host 'Comprobando la IA...' -ForegroundColor Cyan
& $py manage.py ai --test 'Responde sólo: listo' 2>$null | Select-Object -Last 2

# 4. Servidor (waitress, 32 hilos). Su registro queda en instance\servidor.log
New-Item -ItemType Directory -Force 'instance' | Out-Null
$ocupado = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue
if ($ocupado) {
    Write-Host "El puerto $puerto ya está en uso (¿quedó otro servidor abierto?). Ciérralo y vuelve a intentarlo." -ForegroundColor Red
    exit 1
}
Write-Host 'Arrancando el servidor...' -ForegroundColor Cyan
$servidor = Start-Process $py -ArgumentList 'wsgi.py' -NoNewWindow -PassThru `
    -RedirectStandardOutput 'instance\servidor.log' -RedirectStandardError 'instance\servidor-errores.log'
$listo = $false
foreach ($i in 1..60) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$puerto/api/health" | Out-Null
        $listo = $true; break
    } catch { Start-Sleep -Seconds 1 }
    if ($servidor.HasExited) { break }
}
if (-not $listo) {
    Write-Host 'El servidor no arrancó. Revisa instance\servidor-errores.log' -ForegroundColor Red
    exit 1
}

# 5. Link público: Tailscale Funnel (fijo) o, si no está, Cloudflare (cambia cada vez)
$tunel = $null
$publico = $null
$funnel = $false
Remove-Item 'instance\link_publico.txt' -ErrorAction SilentlyContinue
if (-not $SinTunel) {
    $ts = Get-Command tailscale -ErrorAction SilentlyContinue
    $ts = if ($ts) { $ts.Source } else { Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe' }
    if (Test-Path $ts) {
        $estado = $null
        try { $estado = (& $ts status --json 2>$null | Out-String) | ConvertFrom-Json } catch { }
        if ($estado -and $estado.BackendState -eq 'Running' -and $estado.Self.DNSName) {
            Write-Host 'Publicando con Tailscale Funnel (link fijo)...' -ForegroundColor Cyan
            # --bg deja la publicación activa; al apagar este script se retira (funnel reset).
            & $ts funnel --bg $puerto 2>&1 | Out-Host
            if ($LASTEXITCODE -eq 0) {
                $publico = 'https://' + $estado.Self.DNSName.TrimEnd('.')
                $funnel = $true
            } else {
                Write-Host 'Funnel no se pudo activar. La primera vez hay que permitirlo en el enlace que muestra Tailscale arriba.' -ForegroundColor Yellow
            }
        } else {
            Write-Host 'Tailscale está instalado pero sin sesión: ábrelo e inicia sesión para tener el link fijo.' -ForegroundColor Yellow
        }
    }
    if (-not $publico) {
        $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
        $cf = if ($cf) { $cf.Source } else { Join-Path ${env:ProgramFiles(x86)} 'cloudflared\cloudflared.exe' }
        if (Test-Path $cf) {
            Write-Host 'Abriendo el link de Cloudflare (cambia cada vez)...' -ForegroundColor Cyan
            Remove-Item 'instance\tunel.log' -ErrorAction SilentlyContinue
            $tunel = Start-Process $cf -ArgumentList "tunnel --url http://127.0.0.1:$puerto --no-autoupdate --logfile instance\tunel.log" `
                -NoNewWindow -PassThru -RedirectStandardError 'instance\tunel-salida.log'
            foreach ($i in 1..45) {
                Start-Sleep -Seconds 1
                $log = Get-Content 'instance\tunel.log', 'instance\tunel-salida.log' -Raw -ErrorAction SilentlyContinue
                if ($log -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $publico = $Matches[0]; break }
            }
            if (-not $publico) {
                Write-Host 'No se pudo abrir el túnel (¿hay internet?). La app sigue disponible en la red local.' -ForegroundColor Yellow
            }
        } else {
            Write-Host 'Sin link público: instala Tailscale (link fijo) o cloudflared. Ver docs/DEMO_20_USUARIOS.md' -ForegroundColor Yellow
        }
    }
    if ($publico) {
        # El nombre tarda unos segundos en responder desde internet.
        foreach ($i in 1..30) {
            try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "$publico/api/health" | Out-Null; break }
            catch { Start-Sleep -Seconds 2 }
        }
        # La app lo lee para el botón «Compartir (QR)».
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'instance\link_publico.txt'), $publico)
        try { Set-Clipboard $publico } catch { }
    }
}

# 6. Resumen
# Sólo adaptadores con salida a internet (se descartan los virtuales de WSL o Hyper-V).
$ips = Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.IPv4DefaultGateway } |
    ForEach-Object { $_.IPv4Address.IPAddress }
Write-Host ''
Write-Host ('=' * 66) -ForegroundColor DarkCyan
Write-Host '  UFG Knowledge Hub está encendido' -ForegroundColor White
Write-Host "  En esta PC:        http://127.0.0.1:$puerto"
foreach ($ip in $ips) { Write-Host "  Misma red Wi-Fi:   http://${ip}:$puerto" }
if ($publico) {
    Write-Host ''
    Write-Host "  LINK PARA COMPARTIR (celular o compu, desde cualquier lugar):" -ForegroundColor Green
    Write-Host "      $publico" -ForegroundColor Green
    Write-Host ($(if ($funnel) { '  Link FIJO: es el mismo cada vez que enciendas el servidor.' } else { '  Este link cambia cada vez (para uno fijo: Tailscale).' }))
    Write-Host '  (ya está copiado: pégalo en el grupo de WhatsApp) - o que escaneen este QR:'
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    & $py -c "import qrcode, sys; q = qrcode.QRCode(border=2); q.add_data(sys.argv[1]); q.print_ascii(invert=True)" $publico
    Write-Host '  El mismo QR está en la app: menú > Compartir (QR).'
}
Write-Host ''
Write-Host '  Para apagar todo: Ctrl+C o cierra esta ventana.' -ForegroundColor DarkGray
Write-Host ('=' * 66) -ForegroundColor DarkCyan
if (-not $SinNavegador) { Start-Process "http://127.0.0.1:$puerto" }

try {
    while (-not $servidor.HasExited) { Start-Sleep -Seconds 2 }
    Write-Host 'El servidor se detuvo. Revisa instance\servidor-errores.log' -ForegroundColor Yellow
} finally {
    if ($tunel -and -not $tunel.HasExited) { Stop-Process -Id $tunel.Id -Force -ErrorAction SilentlyContinue }
    if ($funnel) { & $ts funnel reset 2>$null | Out-Null }  # la PC deja de estar publicada
    Remove-Item 'instance\link_publico.txt' -ErrorAction SilentlyContinue
    if (-not $servidor.HasExited) {
        # El python del entorno virtual lanza al intérprete real como proceso hijo.
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($servidor.Id)" -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $servidor.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host 'Servidor y túnel apagados.' -ForegroundColor Cyan
}
