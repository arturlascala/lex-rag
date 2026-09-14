#requires -Version 5.1
# Atualizacao incremental semanal do indice lex-rag.
# Prefere o daemon de inferencia (reusa os modelos quentes e e o dono unico do
# Qdrant embedded); se ele estiver fora do ar, cai para a CLI standalone. Assim
# nunca ha dois processos disputando o lock de arquivo do Qdrant.
$ErrorActionPreference = "Stop"

$root    = Split-Path -Parent $PSScriptRoot
$py      = Join-Path $root ".venv\Scripts\python.exe"
$pidFile = Join-Path $root "data\daemon.pid"

$port = $env:LEX_RAG_SERVICE_PORT
if ([string]::IsNullOrEmpty($port)) { $port = "8765" }
$svcHost = $env:LEX_RAG_SERVICE_HOST
if ([string]::IsNullOrEmpty($svcHost)) { $svcHost = "127.0.0.1" }
$base = "http://${svcHost}:${port}"

# Checar os 761 HTMLs do Planalto + embeddings dos alterados leva ~10-15 min;
# o timeout precisa cobrir uma semana movimentada (varios codigos alterados).
$updateTimeoutSec = 3600
# Tempo maximo de espera pelo daemon que ainda esta carregando os modelos.
$healthWaitSec = 180

function Get-DaemonPid {
    if (-not (Test-Path $pidFile)) { return $null }
    $id = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $id) { return $null }
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) { return [int]$id }
    return $null
}

function Test-DaemonHealthy {
    try { Invoke-RestMethod -Uri "$base/health" -TimeoutSec 10 | Out-Null; return $true }
    catch { return $false }
}

$daemonPid = Get-DaemonPid
$healthy = Test-DaemonHealthy

# Processo vivo mas /health mudo: ainda esta aquecendo (~40 s). Se cairmos para
# a CLI agora, ela quebra no lock do Qdrant que o daemon segura — entao espera.
if ($daemonPid -and -not $healthy) {
    Write-Host "[weekly] daemon no ar (PID $daemonPid) mas ainda carregando; aguardando ate ${healthWaitSec}s..."
    $deadline = (Get-Date).AddSeconds($healthWaitSec)
    while (-not $healthy -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        $healthy = Test-DaemonHealthy
    }
    if (-not $healthy) {
        throw "[weekly] daemon (PID $daemonPid) nao respondeu /health em ${healthWaitSec}s; abortando para nao disputar o lock do Qdrant."
    }
}

if ($healthy) {
    $resp = Invoke-RestMethod -Uri "$base/update" -Method Post -ContentType 'application/json' `
        -Body (@{ mode = "delta" } | ConvertTo-Json) -TimeoutSec $updateTimeoutSec
    Write-Host "[weekly] via daemon: $($resp | ConvertTo-Json -Compress)"
} else {
    Write-Host "[weekly] daemon fora do ar; rodando a CLI standalone..."
    & $py -m lex_rag.update.cli --mode delta
}
