param([ValidateSet('start','stop','status')][string]$Action = 'status')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$localDir = Join-Path $taskRoot 'tmp/local-model'
$config = Get-Content -LiteralPath (Join-Path $taskRoot 'data/config/local_model.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$exePath = Join-Path $localDir ('ollama-' + $config.server_version + '/ollama.exe')
$statePath = Join-Path $localDir 'server-owner.json'
$baseUrl = 'http://127.0.0.1:11435'

function Get-LocalVersion {
    try { return (Invoke-RestMethod -Uri ($baseUrl + '/api/version') -TimeoutSec 2).version }
    catch { return $null }
}

if ($Action -eq 'start') {
    $existing = Get-LocalVersion
    if ($existing) {
        if ($existing -ne $config.server_version) { throw 'На выделенном порту работает другая версия. Она не будет остановлена автоматически.' }
        Write-Output ('Локальная Ollama уже отвечает: ' + $baseUrl)
        exit 0
    }
    if (!(Test-Path -LiteralPath $exePath)) { throw 'Переносимая Ollama отсутствует в tmp/. См. docs/agent.md.' }
    if ((Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $config.executable_sha256) { throw 'Хеш исполняемого файла отличается от проверенного.' }
    # Environment belongs only to this child. No startup task or global settings.
    $childEnv = @{OLLAMA_HOST='127.0.0.1:11435'; OLLAMA_MODELS=(Join-Path $localDir 'models'); OLLAMA_NO_CLOUD='1';
        OLLAMA_CONTEXT_LENGTH='8192'; OLLAMA_NUM_PARALLEL='1'; OLLAMA_MAX_LOADED_MODELS='1'; OLLAMA_KEEP_ALIVE='5m'}
    $child = Start-Process -FilePath $exePath -ArgumentList 'serve' -WorkingDirectory $taskRoot -WindowStyle Hidden -Environment $childEnv `
        -RedirectStandardOutput (Join-Path $localDir 'server.stdout.log') -RedirectStandardError (Join-Path $localDir 'server.stderr.log') -PassThru
    @{pid=$child.Id; started_at_ticks=$child.StartTime.ToUniversalTime().Ticks; executable=$exePath} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    for ($i=0; $i -lt 20; $i++) {
        if (Get-LocalVersion) { Write-Output ('Локальная Ollama запущена: ' + $baseUrl + '; облако отключено.'); exit 0 }
        Start-Sleep -Milliseconds 250
    }
    throw 'Сервер не ответил после 20 коротких проверок; проверьте локальные логи tmp/local-model/.'
}

if ($Action -eq 'stop') {
    if (!(Test-Path -LiteralPath $statePath)) { throw 'Нет записи о процессе, запущенном этим скриптом. Чужой процесс не останавливается.' }
    $owner = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $child = Get-Process -Id $owner.pid -ErrorAction SilentlyContinue
    if (!$child) { Write-Output 'Процесс проекта уже остановлен.'; exit 0 }
    if ($child.Path -ne $exePath -or $child.StartTime.ToUniversalTime().Ticks -ne $owner.started_at_ticks) { throw 'PID теперь относится к другому процессу; остановка отменена.' }
    # Release model memory first, using only the fixed loopback endpoint.
    $oldHost = [Environment]::GetEnvironmentVariable('OLLAMA_HOST', 'Process')
    try { $env:OLLAMA_HOST='127.0.0.1:11435'; & $exePath stop 'qwen3:4b' | Out-Null }
    finally { [Environment]::SetEnvironmentVariable('OLLAMA_HOST', $oldHost, 'Process') }
    Stop-Process -Id $child.Id
    $child.WaitForExit(3000) | Out-Null
    Write-Output 'Остановлен только переносимый сервер этого проекта.'
    exit 0
}

$version = Get-LocalVersion
if (!$version) { Write-Output 'Локальный сервер проекта остановлен.'; exit 0 }
$models = (Invoke-RestMethod -Uri ($baseUrl + '/api/ps') -TimeoutSec 3).models
@{endpoint=$baseUrl;server_version=$version;loaded=@($models | Select-Object name,size,size_vram,context_length)} | ConvertTo-Json -Depth 4
