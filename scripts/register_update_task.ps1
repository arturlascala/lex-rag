#requires -Version 5.1
# Registra no Windows Task Scheduler a atualizacao incremental semanal
# (segunda-feira 03h), substituindo o launchd do macOS original.
# Uso:  .\scripts\register_update_task.ps1
$ErrorActionPreference = "Stop"

$root   = Split-Path -Parent $PSScriptRoot
$py     = Join-Path $root ".venv\Scripts\python.exe"
$weekly = Join-Path $PSScriptRoot "weekly_update.ps1"

if (-not (Test-Path $py)) { throw "venv nao encontrado. Rode .\scripts\setup_env.ps1 primeiro." }

# Roda o helper, que prefere o daemon (dono unico do Qdrant) e cai para a CLI se
# ele estiver fora do ar -- evitando conflito de lock com um daemon em execucao.
$action   = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$weekly`"" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 3am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName "lex-rag-update" -Action $action -Trigger $trigger -Settings $settings `
    -Description "lex-rag: atualizacao incremental semanal" -Force | Out-Null

Write-Host "Tarefa 'lex-rag-update' registrada (segunda 03h)."
