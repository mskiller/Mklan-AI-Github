param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Error "Missing $EnvFile. Copy .env.example to .env and fill in local values."
}

$content = Get-Content -LiteralPath $EnvFile -Raw
$requiredChanged = @(
    "MEDIA_INDEXER_POSTGRES_PASSWORD",
    "MEDIA_INDEXER_SESSION_SECRET"
)

$failed = $false
foreach ($name in $requiredChanged) {
    $match = [regex]::Match($content, "(?m)^$name=(.*)$")
    if (-not $match.Success) {
        Write-Host "FAIL $name is missing." -ForegroundColor Red
        $failed = $true
        continue
    }
    $value = $match.Groups[1].Value.Trim()
    if ($value -eq "" -or $value -like "*change-me*") {
        Write-Host "FAIL $name still uses an insecure placeholder." -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "OK   $name" -ForegroundColor Green
    }
}

$cors = [regex]::Match($content, "(?m)^STUDIO_CORS_ORIGINS=(.*)$")
if ($cors.Success -and $cors.Groups[1].Value.Trim() -eq "*") {
    Write-Host "WARN STUDIO_CORS_ORIGINS is wildcard. Use explicit origins before LAN or internet exposure." -ForegroundColor Yellow
}

$apiKey = [regex]::Match($content, "(?m)^STUDIO_API_KEY=(.*)$")
if (-not $apiKey.Success -or $apiKey.Groups[1].Value.Trim() -eq "") {
    Write-Host "WARN STUDIO_API_KEY is not set. V2 APIs are local-trust only." -ForegroundColor Yellow
}

if ($failed) {
    exit 1
}

Write-Host "Environment check completed." -ForegroundColor Green

