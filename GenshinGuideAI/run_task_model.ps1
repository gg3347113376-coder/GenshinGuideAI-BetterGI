# Start a local model server with project-only environment settings.
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$modelRoot = Join-Path $workspaceRoot 'dependencies/Ollama'
$endpoint = 'http://127.0.0.1:11435'
try { $tags = Invoke-RestMethod ($endpoint + '/api/tags') -TimeoutSec 3 } catch { $tags = $null }
if ($null -eq $tags) {
    $ollama = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
    if (-not (Test-Path -LiteralPath $ollama)) { throw '未找到已安装的 Ollama。' }
    if (-not (Test-Path -LiteralPath (Join-Path $modelRoot 'models'))) { throw '缺少项目的模型目录。' }
    $names = @('OLLAMA_HOST','OLLAMA_MODELS','OLLAMA_NUM_PARALLEL','OLLAMA_MAX_LOADED_MODELS','TEMP','TMP')
    $saved = @{}
    foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    try {
        $env:OLLAMA_HOST = '127.0.0.1:11435'
        $env:OLLAMA_MODELS = Join-Path $modelRoot 'models'
        $env:OLLAMA_NUM_PARALLEL = '1'
        $env:OLLAMA_MAX_LOADED_MODELS = '1'
        $env:TEMP = Join-Path $workspaceRoot 'dependencies/GuideWorkbench/temp'
        $env:TMP = $env:TEMP
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $process = Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $modelRoot "server-$stamp.stdout.log") -RedirectStandardError (Join-Path $modelRoot "server-$stamp.stderr.log")
        Set-Content -LiteralPath (Join-Path $modelRoot 'server.pid') -Value $process.Id
    } finally {
        foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $tags = Invoke-RestMethod ($endpoint + '/api/tags') -TimeoutSec 2; break } catch { }
    }
}
if ($null -eq $tags) { throw '本地模型服务未启动成功，请检查 dependencies/Ollama 下的服务日志。' }
if (-not ($tags.models | Where-Object name -EQ 'qwen3.5:4b-q4_K_M')) { throw '本机服务尚未安装指定模型；不会自动下载或替换。' }
Write-Host '离线任务模型已就绪：http://127.0.0.1:11435（不操作游戏）'
