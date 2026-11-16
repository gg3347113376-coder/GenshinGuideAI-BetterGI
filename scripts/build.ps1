param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$out = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $out) { throw "OutputDirectory must be a new directory: $out" }
$project = Join-Path $repo 'BetterGI\BetterGenshinImpact\BetterGenshinImpact.csproj'
$bgi = Join-Path $out 'BetterGI'
& dotnet publish $project -c Release -p:Platform=x64 -r win-x64 --self-contained true -o $bgi
if ($LASTEXITCODE -ne 0) { throw 'dotnet publish failed' }
$dll = Join-Path $bgi 'BetterGI.dll'
$cap = @{
    schema_version='1.0.0'; api='genshin.runTeleportWalkSmoke'
    bettergi_dll_sha256=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    scope='selected unlocked waypoint -> 600ms forward movement -> release and stop verification'
    live_verified=$false; reason='new build; no gameplay execution'; self_contained=$true
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $bgi 'guideai-live-capability.json'), ($cap | ConvertTo-Json), $utf8)
& $Python (Join-Path $repo 'GenshinGuideAI\tools\run_live_smoke.py') --bettergi $bgi
if ($LASTEXITCODE -ne 0) { throw 'Fixed smoke script preparation failed' }
Copy-Item -LiteralPath (Join-Path $repo 'BetterGI\LICENSE') -Destination (Join-Path $bgi 'LICENSE.BetterGI.txt')
Write-Output "Built: $bgi"
Write-Output 'Gameplay was not started or verified.'
