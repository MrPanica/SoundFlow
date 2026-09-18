<#
.SYNOPSIS
    SoundFlow Studio - Build and GitHub Release Script.
.DESCRIPTION
    Builds SoundFlow.exe via PyInstaller and uploads it to GitHub Releases.
.EXAMPLE
    .\scripts\build_and_release.ps1 -Tag v1.0.0
    .\scripts\build_and_release.ps1 -BuildOnly
#>

param(
    [string]$Tag = "v1.0.0",
    [string]$Title = "",
    [string]$Notes = "",
    [switch]$BuildOnly,
    [switch]$NoBuild,
    [switch]$PushTag,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$argsList = @()
if ($Clean) { $argsList += "--clean" }
if ($BuildOnly) { $argsList += "--build-only" }
if ($NoBuild) { $argsList += "--no-build" }
if ($PushTag) { $argsList += "--push-tag" }
if ($Tag) { $argsList += @("--tag", $Tag) }
if ($Title) { $argsList += @("--title", $Title) }
if ($Notes) { $argsList += @("--notes", $Notes) }

python "$ScriptDir\build_and_release.py" @argsList
