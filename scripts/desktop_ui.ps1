param([ValidateSet('start','stop','status')][string]$Action='status',[ValidateRange(1024,65535)][int]$Port=8521)
$ErrorActionPreference='Stop'
$uiRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$projectRoot=Split-Path (Split-Path $uiRoot -Parent) -Parent
$python=Join-Path $projectRoot 'tmp/kp3-ui-cpython312/Scripts/python.exe'
$ownerPath=Join-Path $uiRoot 'tmp/desktop-ui-owner.json'
$url='http://127.0.0.1:'+ $Port
if($Action -eq 'status'){
 try{Invoke-WebRequest -Uri ($url+'/_stcore/health') -TimeoutSec 3 | Out-Null;Write-Output ('Интерфейс доступен: '+$url)}catch{Write-Output 'Интерфейс не отвечает.'};exit 0
}
if($Action -eq 'stop'){
 if(!(Test-Path -LiteralPath $ownerPath)){throw 'Нет квитанции собственного процесса. Остановка отменена.'}
 $owner=Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
 $uiProcess=Get-Process -Id $owner.pid -ErrorAction SilentlyContinue
 if(!$uiProcess){Write-Output 'Собственный процесс уже остановлен.';exit 0}
 if($uiProcess.Path -ne $owner.executable -or $uiProcess.StartTime.ToUniversalTime().Ticks -ne $owner.started_at_ticks){throw 'Владелец PID изменился. Остановка отменена.'}
 Stop-Process -Id $uiProcess.Id;Write-Output 'Остановлен только собственный интерфейс.';exit 0
}
if(!(Test-Path -LiteralPath $python)){throw 'Не найден прежний отдельный UI venv. Установка автоматически не выполняется.'}
if(!(Test-Path -LiteralPath (Join-Path $uiRoot 'tmp/service-context.json'))){throw 'Сначала подготовьте доверенный каталог/контекст в tmp. См. docs/kp3/desktop_ui_v1.md.'}
try{Invoke-WebRequest -Uri ($url+'/_stcore/health') -TimeoutSec 2 | Out-Null;Write-Output ('На порту уже есть интерфейс: '+$url);exit 0}catch{}
$poppler='C:/Users/Value/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
$childEnv=@{KP3_DESKTOP_CONTEXT=(Join-Path $uiRoot 'tmp/service-context.json');KP3_DESKTOP_HISTORY=(Join-Path $uiRoot 'tmp/desktop/history');PYTHONUTF8='1';PATH=($poppler+';'+[Environment]::GetEnvironmentVariable('PATH','Process'))}
$uiArgs=@('-m','streamlit','run','app_kp3/desktop_app.py','--server.address=127.0.0.1',('--server.port='+$Port),'--server.headless=true','--server.fileWatcherType=none','--browser.gatherUsageStats=false','--theme.base=light','--theme.primaryColor=#07865b','--theme.backgroundColor=#f4f6f4','--theme.secondaryBackgroundColor=#f7f9f7')
$uiProcess=Start-Process -FilePath $python -ArgumentList $uiArgs -WorkingDirectory $uiRoot -WindowStyle Hidden -Environment $childEnv -RedirectStandardOutput (Join-Path $uiRoot 'tmp/desktop.stdout.log') -RedirectStandardError (Join-Path $uiRoot 'tmp/desktop.stderr.log') -PassThru
@{pid=$uiProcess.Id;started_at_ticks=$uiProcess.StartTime.ToUniversalTime().Ticks;executable=$uiProcess.Path;port=$Port;url=$url} | ConvertTo-Json | Set-Content -LiteralPath $ownerPath -Encoding utf8
Write-Output ('Запущен новый интерфейс: '+$url)
