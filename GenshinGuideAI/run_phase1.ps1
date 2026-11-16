param(
    [string]$Output = "",
    [string]$Model = "qwen3.5:4b-q4_K_M",
    [string]$ModelHost = "http://127.0.0.1:11435"
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pythonPath = Join-Path $workspaceRoot 'dependencies/GuideWorkbench/venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "缺少现有 Python 环境，请按 docs/PHASE1.md 安装依赖。" }
if (-not $Output) {
    $Output = Join-Path $workspaceRoot ('outputs/GenshinGuideAI/phase1/natlan-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$previousUtf8 = $env:PYTHONUTF8
try {
    $env:PYTHONUTF8 = '1'
    Write-Host '分析本地攻略并生成任务计划；不操作游戏。'
    & $pythonPath -B (Join-Path $PSScriptRoot 'tools/plan_guide.py') `
        --video (Join-Path $workspaceRoot 'downloads/GuideWorkbench/natlan-p4/guide-video.mp4') `
        --transcript (Join-Path $workspaceRoot 'downloads/GuideWorkbench/natlan-p4/transcript.json') `
        --audio (Join-Path $workspaceRoot 'downloads/GuideWorkbench/natlan-p4/source.m4a') `
        --asr-model (Join-Path $workspaceRoot 'dependencies/GuideWorkbench/models/faster-whisper-small') `
        --output $Output --start 0 --end 17.22 --frames '1,10,15,17' `
        --id natlan_p4_phase1 --name '隆崛坡攻略：传送至首个宝箱' `
        --source-url 'https://www.bilibili.com/video/BV14Z421L7DN/?p=4' --model $Model --host $ModelHost
    if ($LASTEXITCODE -eq 2) { Write-Warning "计划复核未通过，原因和证据见 $Output/report.html" }
    elseif ($LASTEXITCODE -ne 0) { throw "计划生成失败，原始证据与失败记录保留在 $Output" }
    Write-Host (Join-Path $Output 'report.html')
} finally {
    $env:PYTHONUTF8 = $previousUtf8
}
