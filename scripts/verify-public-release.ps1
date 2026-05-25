param(
    [string]$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$errors = New-Object System.Collections.Generic.List[string]

$forbiddenDirs = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
@(
    "node_modules",
    ".next",
    "dist",
    "dist-ssr",
    ".pytest_cache",
    "__pycache__",
    ".cache",
    ".vite",
    "htmlcov",
    ".tox",
    ".nox",
    ".venv",
    "venv"
) | ForEach-Object { [void]$forbiddenDirs.Add($_) }

$forbiddenExtensions = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
@(
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-journal",
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".gguf",
    ".onnx",
    ".bin",
    ".h5",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tiff",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".wav",
    ".mp3",
    ".flac",
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".log"
) | ForEach-Object { [void]$forbiddenExtensions.Add($_) }

$textExtensions = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
@(
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
    ".conf"
) | ForEach-Object { [void]$textExtensions.Add($_) }

$contentPatterns = @(
    @{ Pattern = "MsKiller"; Label = "personal username" },
    @{ Pattern = "J:\\"; Label = "personal drive path" },
    @{ Pattern = "C:\\Users\\MsKiller"; Label = "personal user path" },
    @{ Pattern = "Mklan-Noob"; Label = "private model name" },
    @{ Pattern = "codex-real-smoke-lora"; Label = "private smoke-test artifact name" },
    @{ Pattern = "docs/screenshots/[^`r`n]+\\.(png|jpg|jpeg|webp)"; Label = "missing screenshot reference" },
    @{ Pattern = "[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo)\\."; Label = "personal email-like address" }
)

function Add-Error([string]$Message) {
    [void]$errors.Add($Message)
}

function Test-AllowedDataFile([string]$RelativePath) {
    if ($RelativePath -eq "data/README.md") { return $true }
    if ($RelativePath -like "data/*/README.md") { return $true }
    if ($RelativePath -like "data/*/.gitkeep") { return $true }
    if ($RelativePath -like "data/wildcards/starter/*.txt") { return $true }
    return $false
}

function Test-TextFile([System.IO.FileInfo]$File) {
    if ($textExtensions.Contains($File.Extension)) { return $true }
    $name = $File.Name.ToLowerInvariant()
    return $name -in @("dockerfile", "dockerfile.gpu", ".gitignore", ".env.example", "license")
}

$files = Get-ChildItem -LiteralPath $rootPath -Recurse -Force -File -ErrorAction SilentlyContinue

foreach ($file in $files) {
    $relative = [System.IO.Path]::GetRelativePath($rootPath, $file.FullName).Replace("\", "/")
    $parts = $relative -split "/"

    if ($parts[0] -eq ".git") {
        continue
    }

    if ($file.Name -eq ".env" -or ($file.Name -like ".env.*" -and $file.Name -ne ".env.example")) {
        Add-Error "Forbidden environment file: $relative"
    }

    foreach ($part in $parts) {
        if ($forbiddenDirs.Contains($part)) {
            Add-Error "Forbidden generated/dependency directory content: $relative"
            break
        }
    }

    if ($forbiddenExtensions.Contains($file.Extension)) {
        Add-Error "Forbidden artifact/media/model file: $relative"
    }

    if ($relative -like "data/*" -and -not (Test-AllowedDataFile $relative)) {
        Add-Error "Unexpected committed runtime data file: $relative"
    }

    if ($relative -like "media-indexer/docs/screenshots/*") {
        Add-Error "Screenshot asset should not be committed: $relative"
    }

    if ((Test-TextFile $file) -and $relative -ne "scripts/verify-public-release.ps1") {
        $content = Get-Content -LiteralPath $file.FullName -Raw
        foreach ($pattern in $contentPatterns) {
            if ($content -match $pattern.Pattern) {
                Add-Error "Found $($pattern.Label) in $relative"
            }
        }
    }
}

if ($errors.Count -gt 0) {
    Write-Host "Public release verification failed:" -ForegroundColor Red
    $errors | Sort-Object -Unique | ForEach-Object {
        Write-Host " - $_" -ForegroundColor Red
    }
    exit 1
}

Write-Host "Public release verification passed for $rootPath" -ForegroundColor Green
