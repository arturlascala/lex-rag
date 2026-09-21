#requires -Version 5.1
# Task runner do lex-rag para Windows (equivalente ao Makefile).
# Uso:  .\tasks.ps1 <alvo>
#   setup | smoke | bootstrap | update | descobrir-novas
#   serve | daemon-start | daemon-stop | daemon-status   (daemon de inferencia)
#   snapshot-criar | snapshot-restaurar <zip|URL> [-Forcar]   (corpus pre-montado)
#   mcp | test | lint | clean
param(
    [Parameter(Position = 0)][string]$Target = "help",
    [Parameter(Position = 1)][string]$Arg,
    [switch]$Forcar
)
$ErrorActionPreference = "Stop"

$root    = $PSScriptRoot
$py      = Join-Path $root ".venv\Scripts\python.exe"
$pyw     = Join-Path $root ".venv\Scripts\pythonw.exe"
$pidFile = Join-Path $root "data\daemon.pid"

function Assert-Venv {
    if (-not (Test-Path $py)) {
        throw "venv nao encontrado. Rode primeiro:  .\scripts\setup_env.ps1"
    }
}

function Get-ServiceUrl {
    $port = $env:LEX_RAG_SERVICE_PORT
    if ([string]::IsNullOrEmpty($port)) { $port = "8765" }
    $svcHost = $env:LEX_RAG_SERVICE_HOST
    if ([string]::IsNullOrEmpty($svcHost)) { $svcHost = "127.0.0.1" }
    return "http://${svcHost}:${port}"
}

function Get-DaemonPid {
    if (-not (Test-Path $pidFile)) { return $null }
    $id = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $id) { return $null }
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) { return [int]$id }
    return $null
}

switch ($Target.ToLower()) {
    "setup"     { & (Join-Path $root "scripts\setup_env.ps1") }
    "smoke"     { Assert-Venv; & $py (Join-Path $root "scripts\smoke_test.py") }
    "bootstrap" { Assert-Venv; & $py (Join-Path $root "scripts\bootstrap_full_index.py") }
    "update"    { Assert-Venv; & $py -m lex_rag.update.cli --mode delta }
    "descobrir-novas" {
        # Leis novas desde o ultimo ponto (LexML + Planalto; nao toca o Qdrant,
        # pode rodar com o daemon no ar) e a verificacao do parser sobre elas.
        Assert-Venv
        & $py (Join-Path $root "scripts\descobrir_novas.py")
        & $py (Join-Path $root "scripts\verificar_parser.py") --novos --baixar
    }
    "serve"     { Assert-Venv; & $py -m lex_rag.service }
    "daemon-start" {
        Assert-Venv
        $existing = Get-DaemonPid
        if ($existing) { Write-Host "[daemon] ja esta no ar (PID $existing)."; break }
        $dataDir = Join-Path $root "data"
        if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }
        $outLog = Join-Path $dataDir "daemon.out.log"
        $errLog = Join-Path $dataDir "daemon.err.log"
        # pythonw nao tem console: sem redirecionar, sys.stdout=None quebra o boot.
        # Redirecionar para arquivos da streams validas E deixa logs para depuracao.
        $proc = Start-Process -FilePath $pyw -ArgumentList '-m', 'lex_rag.service' -WorkingDirectory $root `
            -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
        Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
        Write-Host "[daemon] iniciado em background (PID $($proc.Id)). Carregando os modelos (~30-60 s)..."
        Write-Host "[daemon] logs: $outLog"
        Write-Host "[daemon] acompanhe com:  .\tasks.ps1 daemon-status"
    }
    "daemon-stop" {
        $id = Get-DaemonPid
        if (-not $id) {
            Write-Host "[daemon] nao esta no ar."
            if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
            break
        }
        Stop-Process -Id $id -Force
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        Write-Host "[daemon] parado (PID $id). VRAM liberada."
    }
    "daemon-status" {
        $id = Get-DaemonPid
        if ($id) { Write-Host "[daemon] processo no ar (PID $id)." }
        else { Write-Host "[daemon] processo NAO encontrado." }
        $url = (Get-ServiceUrl) + "/health"
        try {
            $resp = Invoke-RestMethod -Uri $url -TimeoutSec 5
            Write-Host "---"
            Write-Host $resp
        } catch {
            Write-Host "[daemon] /health indisponivel ($url). Os modelos ainda podem estar carregando."
        }
    }
    "snapshot-criar" { Assert-Venv; & $py (Join-Path $root "scripts\snapshot.py") criar }
    "snapshot-restaurar" {
        Assert-Venv
        if (-not $Arg) { throw "Uso:  .\tasks.ps1 snapshot-restaurar <arquivo.zip | URL> [-Forcar]" }
        $extra = @(); if ($Forcar) { $extra += "--forcar" }
        & $py (Join-Path $root "scripts\snapshot.py") restaurar $Arg @extra
    }
    "mcp"       { Assert-Venv; & $py -m lex_rag.mcp_server.server }
    "test"      { Assert-Venv; & $py -m pytest -m "not network" -q }
    "lint"      { Assert-Venv; & $py -m ruff check src tests scripts }
    "clean" {
        Get-ChildItem -Path $root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache" } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "[clean] caches removidos."
    }
    default {
        Write-Host "Alvos:"
        Write-Host "  setup | smoke | bootstrap | update | descobrir-novas"
        Write-Host "  serve | daemon-start | daemon-stop | daemon-status   (daemon de inferencia)"
        Write-Host "  snapshot-criar | snapshot-restaurar <zip|URL> [-Forcar]   (corpus pre-montado)"
        Write-Host "  mcp | test | lint | clean"
    }
}
