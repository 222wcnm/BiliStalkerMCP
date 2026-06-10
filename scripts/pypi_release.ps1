[CmdletBinding()]
param(
    [switch]$Upload,
    [switch]$TestPyPI,
    [switch]$SkipTests,
    [switch]$SkipVersionCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PypiToken {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Section
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "PyPI credentials not found: $Path"
    }

    $currentSection = $null
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()

        if ($line -match '^\[([^\]]+)\]$') {
            $currentSection = $Matches[1].Trim()
            continue
        }

        if (
            $currentSection -eq $Section -and
            $line -match '^password\s*[:=]\s*(.+)$'
        ) {
            return $Matches[1].Trim()
        }
    }

    throw "No password found in [$Section] section of $Path"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$projectName = "bili-stalker-mcp"
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"

if (-not (Test-Path $pyprojectPath)) {
    throw "pyproject.toml not found: $pyprojectPath"
}

$pyprojectText = Get-Content -LiteralPath $pyprojectPath -Raw -Encoding UTF8
$versionMatch = [regex]::Match($pyprojectText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Could not parse [project].version from pyproject.toml."
}
$version = $versionMatch.Groups[1].Value

Write-Host "Preparing release for $projectName $version"

if (-not $SkipVersionCheck) {
    $registryUrl = if ($TestPyPI) {
        "https://test.pypi.org/pypi/$projectName/json"
    }
    else {
        "https://pypi.org/pypi/$projectName/json"
    }

    try {
        $registryInfo = Invoke-RestMethod -Uri $registryUrl -Method Get -TimeoutSec 20
        $publishedVersions = $registryInfo.releases.PSObject.Properties.Name
        if ($publishedVersions -contains $version) {
            throw "Version $version already exists in registry. Update version first."
        }
        Write-Host "Version check passed."
    }
    catch {
        $statusCode = $null
        if ($_.Exception.PSObject.Properties.Name -contains "Response" -and $_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }

        if ($statusCode -eq 404) {
            Write-Host "Package not found in target registry yet; continuing."
        }
        elseif ($_.Exception.Message -like "*already exists*") {
            throw
        }
        else {
            Write-Warning "Unable to verify registry version automatically: $($_.Exception.Message)"
        }
    }
}

if (-not $SkipTests) {
    uv run pytest -q
}

if (Test-Path "dist") {
    Get-ChildItem "dist" -File |
    Where-Object { $_.Name -ne ".gitignore" } |
    Remove-Item -Force
}
else {
    New-Item -ItemType Directory -Path "dist" | Out-Null
}

uv build --no-sources
uvx --from twine twine check dist/*

if (-not $Upload) {
    Write-Host ""
    Write-Host "Build and validation completed. Upload skipped."
    Write-Host "To upload, run:"
    if ($TestPyPI) {
        Write-Host "  .\scripts\pypi_release.ps1 -TestPyPI -Upload"
    }
    else {
        Write-Host "  .\scripts\pypi_release.ps1 -Upload"
    }
    exit 0
}

$publishTokenWasSet = Test-Path Env:UV_PUBLISH_TOKEN
$previousPublishToken = if ($publishTokenWasSet) {
    $env:UV_PUBLISH_TOKEN
}
else {
    $null
}

if (-not $publishTokenWasSet) {
    $pypircPath = Join-Path $HOME ".pypirc"
    $pypircSection = if ($TestPyPI) { "testpypi" } else { "pypi" }
    $env:UV_PUBLISH_TOKEN = Get-PypiToken -Path $pypircPath -Section $pypircSection
    Write-Host "Using [$pypircSection] credentials from $pypircPath"
}

try {
    if ($TestPyPI) {
        uv publish `
            --publish-url "https://test.pypi.org/legacy/" `
            --check-url "https://test.pypi.org/simple/" `
            dist/*
        if ($LASTEXITCODE -ne 0) {
            throw "uv publish failed for TestPyPI (exit code $LASTEXITCODE)"
        }
        Write-Host "Upload completed: TestPyPI"
    }
    else {
        uv publish dist/*
        if ($LASTEXITCODE -ne 0) {
            throw "uv publish failed for PyPI (exit code $LASTEXITCODE)"
        }
        Write-Host "Upload completed: PyPI"
    }
}
finally {
    if ($publishTokenWasSet) {
        $env:UV_PUBLISH_TOKEN = $previousPublishToken
    }
    else {
        Remove-Item Env:UV_PUBLISH_TOKEN -ErrorAction SilentlyContinue
    }
}
