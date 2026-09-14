#requires -Version 5.1
# Cria o ambiente do lex-rag nesta maquina (Windows).
# Uso:  .\scripts\setup_env.ps1          (GPU NVIDIA: torch CUDA cu121)
#       .\scripts\setup_env.ps1 -Cpu     (sem GPU dedicada: torch CPU)
param([switch]$Cpu)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot   # ...\lex_rag
$venv = Join-Path $root ".venv"
$py   = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "[setup] Criando venv com Python 3.12 (py -3.12)..."
    py -3.12 -m venv $venv
}

Write-Host "[setup] Atualizando pip..."
& $py -m pip install --upgrade pip

if ($Cpu) {
    Write-Host "[setup] Instalando torch CPU..."
    & $py -m pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
} else {
    Write-Host "[setup] Instalando torch CUDA (cu121) -- senao o pip pega o wheel CPU..."
    & $py -m pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cu121
}

Write-Host "[setup] Instalando lex-rag + deps (dev)..."
Push-Location $root
try { & $py -m pip install -e ".[dev]" } finally { Pop-Location }

Write-Host "[setup] Verificando GPU..."
& $py -c "import torch; print('CUDA disponivel:', torch.cuda.is_available(), '|', (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'))"

Write-Host "[setup] OK. Para usar o corpus pronto:  .\tasks.ps1 snapshot-restaurar <zip ou URL>"
Write-Host "[setup]     ou, para indexar do zero:   .\tasks.ps1 smoke  e depois  .\tasks.ps1 bootstrap"
