$ErrorActionPreference='Stop'
$root='C:\claude_code_project\qq-small-agent'
$data=Join-Path $env:LOCALAPPDATA 'QQ-Small-Agent-Pilot'
New-Item -ItemType Directory -Path $data -Force | Out-Null
$log=Join-Path $data 'command-agent-service.log'
$python=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
if(!(Test-Path -LiteralPath $python)) {throw 'Python 3.13 runtime not found'}
if(!(Test-Path -LiteralPath (Join-Path $root 'qq_command_agent.py'))) {throw 'QQ v2 receiver missing'}
$mutex=New-Object System.Threading.Mutex($false,'Local\QQSmallAccountAgentV2')
$entered=$false
try {
    $entered=$mutex.WaitOne(0)
    if(-not $entered) {
        Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format o)+' second instance blocked')
        exit 8
    }
    Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format o)+' agent supervisor running')
    Set-Location -LiteralPath $root
    & $python -u (Join-Path $root 'qq_command_agent.py') run 2>&1 | ForEach-Object {
       $line=[string]$_
       if($line -match 'token=|Bearer |password|cookie|WebUi Token') {
           $line='[Sensitive log line redacted]'
       }
       Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+' '+$line)
    }
    $code=$LASTEXITCODE
    Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format o)+' agent exited code '+$code)
    exit $code
}
finally {
    if($entered) {$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
