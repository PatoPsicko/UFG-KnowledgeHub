# Publica UFG Knowledge Hub en internet GRATIS con Cloudflare Tunnel (sin cuenta,
# sin abrir puertos del router ni tocar el firewall).
#
#   1. Instala cloudflared una sola vez:   winget install Cloudflare.cloudflared
#   2. Arranca el servidor en otra terminal:   .venv\Scripts\python.exe wsgi.py
#   3. Ejecuta este script:   powershell -ExecutionPolicy Bypass -File scripts\compartir.ps1
#
# Aparecerá una dirección https://algo-al-azar.trycloudflare.com: compártela con
# los 20 compañeros que van a probar. Funciona mientras esta ventana esté abierta;
# al cerrarla la dirección deja de existir (la siguiente vez será otra).

$puerto = if ($env:APP_PORT) { $env:APP_PORT } else { 5001 }

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $posible = Join-Path ${env:ProgramFiles(x86)} 'cloudflared\cloudflared.exe'
    if (Test-Path $posible) { $cloudflared = $posible } else {
        Write-Host 'No encuentro cloudflared. Instálalo con:' -ForegroundColor Yellow
        Write-Host '    winget install Cloudflare.cloudflared'
        Write-Host 'y vuelve a abrir la terminal.'
        exit 1
    }
}

try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$puerto/api/health" | Out-Null
} catch {
    Write-Host "El servidor no responde en el puerto $puerto. Arráncalo primero con:" -ForegroundColor Yellow
    Write-Host '    .venv\Scripts\python.exe wsgi.py'
    exit 1
}

Write-Host "Abriendo túnel hacia http://127.0.0.1:$puerto ..." -ForegroundColor Cyan
Write-Host 'Busca abajo la línea con https://...trycloudflare.com y compártela.' -ForegroundColor Cyan
& $cloudflared tunnel --url "http://127.0.0.1:$puerto" --no-autoupdate
