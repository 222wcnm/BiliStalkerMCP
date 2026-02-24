[CmdletBinding()]
param(
    [switch]$Upload,
    [switch]$TestPyPI,
    [switch]$SkipTests,
    [switch]$SkipVersionCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$projectName = "bili-stalker-mcp"
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"

if (-not (Test-Path $pyprojectPath)) {
    throw "pyproject.toml not found: $pyprojectPath"
}

$pyprojectText = Get-Content -Raw $pyprojectPath
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

uv build
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


if ($TestPyPI) {
    uvx --from twine twine upload --repository testpypi dist/*
    Write-Host "Upload completed: TestPyPI"
}
else {
    uvx --from twine twine upload dist/*
    Write-Host "Upload completed: PyPI"
}
