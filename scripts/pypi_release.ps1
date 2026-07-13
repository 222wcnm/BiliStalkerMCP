[CmdletBinding()]
param(
    [switch]$Upload,
    [switch]$TestPyPI,
    [switch]$SkipTests,
    [switch]$SkipVersionCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param([Parameter(Mandatory)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed (exit code $LASTEXITCODE)."
    }
}

function Get-PypiToken {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Section
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

function Get-DistributionFiles {
    param([Parameter(Mandatory)][string]$DistDirectory)

    $sdists = @(Get-ChildItem -LiteralPath $DistDirectory -Filter "*.tar.gz" -File)
    $wheels = @(Get-ChildItem -LiteralPath $DistDirectory -Filter "*.whl" -File)
    if ($sdists.Count -ne 1 -or $wheels.Count -ne 1) {
        throw "Expected one sdist and one wheel; found $($sdists.Count) sdist(s) and $($wheels.Count) wheel(s)."
    }
    return @($sdists[0], $wheels[0])
}

function Assert-SafeDistributions {
    param([Parameter(Mandatory)][string]$DistDirectory)

    $forbiddenPatterns = @(
        '(^|/)(\.claude|\.codex)(/|$)',
        '(^|/)\.env$',
        '(^|/)\.mcp\.json$',
        '(^|/)BILI_COOKIE\.txt$',
        '(^|/)BILI_REFRESH_TOKEN\.txt$',
        '(^|/)cookie\.json$',
        '(^|/)refresh_token\.json$',
        '(^|/)bili_refresh_token\.json$',
        '(^|/)\.bili_refresh_token$',
        '(^|/)\.bili-cookie-refresh-transaction\.json$',
        '(^|/)\.bili-cookie-refresh-cookie\.stage$',
        '(^|/)\.bili-cookie-refresh-token\.stage$',
        '(^|/)\.bili-cookie-refresh-pending\.json$',
        '(^|/)\.bili-cookie-refresh\.lock$',
        '(^|/)\.bili-cookie-refresh-.*\.tmp$'
    )

    foreach ($artifact in Get-DistributionFiles -DistDirectory $DistDirectory) {
        $entries = @(& tar -tf $artifact.FullName)
        Assert-LastExitCode -Operation "Inspecting $($artifact.Name)"
        $forbiddenEntries = @(
            $entries | Where-Object {
                $entry = $_.Replace('\', '/')
                $forbiddenPatterns | Where-Object { $entry -match $_ }
            }
        )
        if ($forbiddenEntries.Count -gt 0) {
            throw "Distribution contains forbidden local state: $($forbiddenEntries -join ', ')"
        }
    }

    Write-Host "Distribution content checks passed."
}

function Remove-SafeTempDirectory {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $resolved = [IO.Path]::GetFullPath($Path)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a directory outside the system temp root."
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Get-VenvExecutables {
    param([Parameter(Mandatory)][string]$VenvPath)

    if ($IsWindows) {
        return @(
            (Join-Path $VenvPath "Scripts\python.exe"),
            (Join-Path $VenvPath "Scripts\bili-stalker-cookie-setup.exe")
        )
    }
    return @(
        (Join-Path $VenvPath "bin/python"),
        (Join-Path $VenvPath "bin/bili-stalker-cookie-setup")
    )
}

function Test-InstalledEnvironment {
    param(
        [Parameter(Mandatory)][string]$VenvPath,
        [Parameter(Mandatory)][string]$ExpectedVersion
    )

    $executables = Get-VenvExecutables -VenvPath $VenvPath
    $pythonPath = $executables[0]
    $setupPath = $executables[1]
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "Smoke-test Python is missing."
    }
    if (-not (Test-Path -LiteralPath $setupPath)) {
        throw "Packaged bili-stalker-cookie-setup entry point is missing."
    }

    $smokeCode = @'
import asyncio
import os
from importlib import metadata

from packaging.requirements import Requirement

expected = os.environ["BILI_RELEASE_EXPECTED_VERSION"]
os.environ["BILI_ENABLE_COOKIE_REFRESH"] = "false"
assert metadata.version("bili-stalker-mcp") == expected
assert metadata.version("bilibili-api-python") == "17.4.2"
assert metadata.version("filelock") == "3.29.7"
requirements = {
    Requirement(raw).name.casefold(): str(Requirement(raw).specifier)
    for raw in metadata.requires("bili-stalker-mcp") or []
}
assert requirements["bilibili-api-python"] == "==17.4.2"
assert requirements["filelock"] == "==3.29.7"
from bili_stalker_mcp.server import create_server
from bili_stalker_mcp.setup_cookie_refresh import main as setup_main
assert callable(setup_main)
tools = asyncio.run(create_server().list_tools())
assert len(tools) == 10
assert len({tool.name for tool in tools}) == 10
'@

    $hadExpectedVersion = Test-Path Env:BILI_RELEASE_EXPECTED_VERSION
    $previousExpectedVersion = if ($hadExpectedVersion) {
        $env:BILI_RELEASE_EXPECTED_VERSION
    }
    else {
        $null
    }
    try {
        $env:BILI_RELEASE_EXPECTED_VERSION = $ExpectedVersion
        & $pythonPath -I -c $smokeCode
        Assert-LastExitCode -Operation "Installed-package smoke test"
        & $setupPath --help | Out-Null
        Assert-LastExitCode -Operation "Setup entry-point smoke test"
    }
    finally {
        if ($hadExpectedVersion) {
            $env:BILI_RELEASE_EXPECTED_VERSION = $previousExpectedVersion
        }
        else {
            Remove-Item Env:BILI_RELEASE_EXPECTED_VERSION -ErrorAction SilentlyContinue
        }
    }
}

function Test-DistributionArtifacts {
    param(
        [Parameter(Mandatory)][string]$DistDirectory,
        [Parameter(Mandatory)][string]$ExpectedVersion
    )

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("bili-stalker-dist-smoke-" + [guid]::NewGuid())
    try {
        New-Item -ItemType Directory -Path $tempRoot | Out-Null
        $index = 0
        foreach ($artifact in Get-DistributionFiles -DistDirectory $DistDirectory) {
            $index += 1
            $venvPath = Join-Path $tempRoot "venv-$index"
            uv venv $venvPath --python 3.12
            Assert-LastExitCode -Operation "Creating artifact smoke-test environment"
            $pythonPath = (Get-VenvExecutables -VenvPath $venvPath)[0]
            uv pip install --python $pythonPath $artifact.FullName
            Assert-LastExitCode -Operation "Installing $($artifact.Name)"
            Test-InstalledEnvironment -VenvPath $venvPath -ExpectedVersion $ExpectedVersion
        }
    }
    finally {
        Remove-SafeTempDirectory -Path $tempRoot
    }

    Write-Host "Wheel and sdist installation checks passed."
}

function Test-RegistryPackage {
    param(
        [Parameter(Mandatory)][string]$ProjectName,
        [Parameter(Mandatory)][string]$Version,
        [Parameter(Mandatory)][bool]$UseTestPyPI
    )

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("bili-stalker-registry-smoke-" + [guid]::NewGuid())
    try {
        uv venv $tempRoot --python 3.12
        Assert-LastExitCode -Operation "Creating registry smoke-test environment"
        $pythonPath = (Get-VenvExecutables -VenvPath $tempRoot)[0]
        $requirement = "$ProjectName==$Version"
        if ($UseTestPyPI) {
            uv pip install `
                --python $pythonPath `
                --index-url "https://test.pypi.org/simple" `
                --extra-index-url "https://pypi.org/simple" `
                --index-strategy unsafe-best-match `
                $requirement
        }
        else {
            uv pip install --python $pythonPath $requirement
        }
        Assert-LastExitCode -Operation "Installing $requirement from registry"
        Test-InstalledEnvironment -VenvPath $tempRoot -ExpectedVersion $Version
    }
    finally {
        Remove-SafeTempDirectory -Path $tempRoot
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$projectName = "bili-stalker-mcp"
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"
$distDirectory = Join-Path $repoRoot "dist"

if (-not (Test-Path -LiteralPath $pyprojectPath)) {
    throw "pyproject.toml not found: $pyprojectPath"
}

$branch = (& git branch --show-current).Trim()
Assert-LastExitCode -Operation "Reading Git branch"
if ($branch -ne "main") {
    throw "Release must run from main; current branch is '$branch'."
}
$dirtyState = @(& git status --porcelain --untracked-files=all)
Assert-LastExitCode -Operation "Reading Git worktree status"
if ($dirtyState.Count -gt 0) {
    throw "Release requires a clean Git worktree."
}

$pyprojectText = Get-Content -LiteralPath $pyprojectPath -Raw -Encoding UTF8
$versionMatch = [regex]::Match($pyprojectText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Could not parse [project].version from pyproject.toml."
}
$version = $versionMatch.Groups[1].Value
$existingTag = @(& git tag --list "v$version")
Assert-LastExitCode -Operation "Checking release tag"
if ($existingTag.Count -gt 0) {
    throw "Git tag v$version already exists."
}

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
            throw "Unable to verify registry version: $($_.Exception.Message)"
        }
    }
}

uv sync --locked --all-extras --dev
Assert-LastExitCode -Operation "Installing locked environment"
uv lock --check
Assert-LastExitCode -Operation "Checking uv.lock"

if (-not $SkipTests) {
    uv run pytest -q -p no:cacheprovider
    Assert-LastExitCode -Operation "pytest"
    uv run black --check bili_stalker_mcp tests scripts
    Assert-LastExitCode -Operation "black"
    uv run isort --check-only bili_stalker_mcp tests scripts
    Assert-LastExitCode -Operation "isort"
    uv run flake8 bili_stalker_mcp tests scripts
    Assert-LastExitCode -Operation "flake8"
    uv run mypy bili_stalker_mcp
    Assert-LastExitCode -Operation "mypy"
}

if (Test-Path -LiteralPath $distDirectory) {
    Get-ChildItem -LiteralPath $distDirectory -File |
        Where-Object { $_.Name -ne ".gitignore" } |
        Remove-Item -Force
}
else {
    New-Item -ItemType Directory -Path $distDirectory | Out-Null
}

uv build --no-sources
Assert-LastExitCode -Operation "Building distributions"
Assert-SafeDistributions -DistDirectory $distDirectory
uvx --from twine twine check dist/*
Assert-LastExitCode -Operation "twine check"
Test-DistributionArtifacts -DistDirectory $distDirectory -ExpectedVersion $version

if (-not $Upload) {
    Write-Host "Build and validation completed. Upload skipped."
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
        Assert-LastExitCode -Operation "Uploading to TestPyPI"
        Write-Host "Upload completed: TestPyPI"
    }
    else {
        uv publish dist/*
        Assert-LastExitCode -Operation "Uploading to PyPI"
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

$verified = $false
for ($attempt = 1; $attempt -le 5; $attempt += 1) {
    try {
        Test-RegistryPackage `
            -ProjectName $projectName `
            -Version $version `
            -UseTestPyPI ([bool]$TestPyPI)
        $verified = $true
        break
    }
    catch {
        if ($attempt -eq 5) {
            throw
        }
        Write-Host "Registry package is not ready yet; retrying in 5 seconds."
        Start-Sleep -Seconds 5
    }
}
if (-not $verified) {
    throw "Registry installation verification did not complete."
}

Write-Host "Registry installation verification passed."
