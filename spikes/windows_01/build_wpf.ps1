$ErrorActionPreference = 'Stop'
$spikeRoot = $PSScriptRoot
$spikeOutput = [IO.Path]::GetFullPath((Join-Path $spikeRoot '../../tmp/wpf-build'))
New-Item -ItemType Directory -Path $spikeOutput -Force | Out-Null
$spikeFramework = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319'
$spikeCompiler = Join-Path $spikeFramework 'csc.exe'
& $spikeCompiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$spikeOutput/WpfSpike.exe" "/win32manifest:$spikeRoot/wpf.manifest" "/reference:$spikeFramework/WPF/PresentationFramework.dll" "/reference:$spikeFramework/WPF/PresentationCore.dll" "/reference:$spikeFramework/WPF/WindowsBase.dll" /reference:System.Xaml.dll /reference:System.Web.Extensions.dll "/reference:$spikeFramework/WPF/UIAutomationTypes.dll" (Join-Path $spikeRoot 'WpfSpike.cs')
if ($LASTEXITCODE -ne 0) { throw 'WPF compilation failed' }
@'
<?xml version="1.0" encoding="utf-8"?>
<configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8"/></startup><runtime><AppContextSwitchOverrides value="Switch.System.Windows.DoNotScaleForDpiChanges=false;Switch.System.Windows.DoNotUsePresentationDpiCapabilityTier2OrGreater=false"/></runtime></configuration>
'@ | Set-Content -LiteralPath (Join-Path $spikeOutput 'WpfSpike.exe.config') -Encoding utf8
Get-Item -LiteralPath (Join-Path $spikeOutput 'WpfSpike.exe') | Select-Object Name,Length
