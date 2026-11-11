param([ValidateSet('diagnose','start','status','stop')][string]$Action='diagnose',[ValidateRange(1024,65535)][int]$Port=8522)
$ErrorActionPreference='Stop'
$releaseRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$workspaceRoot=Split-Path (Split-Path $releaseRoot -Parent) -Parent
$uiPython=Join-Path $workspaceRoot 'tmp/kp3-ui-cpython312/Scripts/python.exe'
$corePython='C:/msys64/ucrt64/bin/python.exe'
$manifest=Join-Path $releaseRoot 'data/releases/kp3_rc1/manifest.json'
$ownerPath=Join-Path $releaseRoot 'tmp/release-ui-owner.json'
$context=Join-Path $releaseRoot 'tmp/service-context.json'
$resources=Join-Path $releaseRoot 'tmp/freeze-resources17.json'
$url='http://127.0.0.1:'+$Port
function Own-Process($owner){
 $releaseProcess=Get-Process -Id $owner.pid -ErrorAction SilentlyContinue
 if(!$releaseProcess){return $null}
 if($releaseProcess.Path -ne $owner.executable -or $releaseProcess.StartTime.ToUniversalTime().Ticks -ne $owner.started_at_ticks){throw 'PID принадлежит другому процессу. Он не будет остановлен или принят за выпуск.'}
 return $releaseProcess
}
if($Action -eq 'stop'){
 if(!(Test-Path -LiteralPath $ownerPath)){throw 'Нет квитанции собственного процесса выпуска.'}
 $owner=Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
 $releaseProcess=Own-Process $owner
 if($releaseProcess){Stop-Process -Id $releaseProcess.Id;Write-Output 'Остановлен только собственный UI кандидата выпуска.'}else{Write-Output 'Собственный UI уже остановлен.'}
 exit 0
}
if(!(Test-Path -LiteralPath $corePython)){throw 'Нет проверенного основного Python. Установка автоматически не выполняется.'}
$stamp=[Guid]::NewGuid().ToString('N')
$report=Join-Path $releaseRoot ('tmp/release-readiness-'+$stamp+'.json')
Push-Location -LiteralPath $releaseRoot
try{
 & $corePython -X utf8 -I scripts/check_kp3_release.py --profile B --context $context --resources $resources --report $report
 if($LASTEXITCODE -ne 0){throw ('Кандидат не готов. Диагностика: '+$report)}
 if($Action -eq 'diagnose'){Write-Output ('B готов без модели. A/C требуют отдельной проверки. Диагностика: '+$report);exit 0}
 if(!(Test-Path -LiteralPath $uiPython)){throw 'Отдельный UI venv не найден. Основной Python и пакеты не меняются.'}
 $uiReport=Join-Path $releaseRoot ('tmp/release-ui-readiness-'+$stamp+'.json')
 & $uiPython -X utf8 -I scripts/check_kp3_release.py --profile UI --context $context --resources $resources --report $uiReport
 if($LASTEXITCODE -ne 0){throw ('Зависимости UI не готовы. Диагностика: '+$uiReport)}
 $manifestHash=(Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
 $releaseId=(Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).release_id
 $existing=$null
 try{$existing=Invoke-WebRequest -Uri ($url+'/_stcore/health') -TimeoutSec 2}catch{}
 if($existing){
  if(!(Test-Path -LiteralPath $ownerPath)){throw 'Порт занят процессом без квитанции выпуска. Он не будет принят за наш UI.'}
  $owner=Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
  $releaseProcess=Own-Process $owner
  if(!$releaseProcess -or $owner.port -ne $Port -or $owner.release_id -ne $releaseId -or $owner.manifest_sha256 -ne $manifestHash){throw 'Состояние порта и кандидата не совпадает с собственной квитанцией.'}
  Write-Output ('Проверенный UI кандидата доступен: '+$url);exit 0
 }
 if($Action -eq 'status'){throw 'UI кандидата сейчас не запущен. B-готовность проверена отдельно.'}
 $poppler='C:/Users/Value/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
 $childEnv=@{KP3_DESKTOP_CONTEXT=$context;KP3_DESKTOP_HISTORY=(Join-Path $releaseRoot 'tmp/rc1/history');PYTHONUTF8='1';PATH=($poppler+';'+[Environment]::GetEnvironmentVariable('PATH','Process'))}
 $uiArgs=@('-m','streamlit','run','app_kp3/desktop_app.py','--server.address=127.0.0.1',('--server.port='+$Port),'--server.headless=true','--server.fileWatcherType=none','--browser.gatherUsageStats=false','--theme.base=light','--theme.primaryColor=#07865b','--theme.backgroundColor=#f4f6f4','--theme.secondaryBackgroundColor=#f7f9f7')
 $releaseProcess=Start-Process -FilePath $uiPython -ArgumentList $uiArgs -WorkingDirectory $releaseRoot -WindowStyle Hidden -Environment $childEnv -RedirectStandardOutput (Join-Path $releaseRoot ('tmp/release-ui-'+$stamp+'.stdout.log')) -RedirectStandardError (Join-Path $releaseRoot ('tmp/release-ui-'+$stamp+'.stderr.log')) -PassThru
 @{pid=$releaseProcess.Id;started_at_ticks=$releaseProcess.StartTime.ToUniversalTime().Ticks;executable=$releaseProcess.Path;port=$Port;url=$url;release_id=$releaseId;manifest_sha256=$manifestHash} | ConvertTo-Json | Set-Content -LiteralPath $ownerPath -Encoding utf8
 for($i=0;$i -lt 20;$i++){
  try{$ready=Invoke-WebRequest -Uri ($url+'/_stcore/health') -TimeoutSec 1;if($ready.StatusCode -eq 200 -and $ready.Content -eq 'ok'){Write-Output ('Запущен UI кандидата: '+$url);exit 0}}catch{}
  Start-Sleep -Milliseconds 250
 }
 throw 'Собственный процесс создан, но UI не подтвердил готовность. Смотрите отдельные логи; автоматического повторного запуска нет.'
}finally{Pop-Location}
