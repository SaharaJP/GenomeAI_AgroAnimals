$ErrorActionPreference = "Stop"

# GenomeAI AgroAnimals installer (Windows 10/11)
# Установка в пользовательский каталог (без прав администратора):
# %LOCALAPPDATA%\GenomeAI_AgroAnimals

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

$AppRoot = $env:GENOMEAI_APP_ROOT
if ([string]::IsNullOrWhiteSpace($AppRoot)) {
  $AppRoot = Join-Path $env:LOCALAPPDATA "GenomeAI_AgroAnimals"
}

$VenvDir = Join-Path $AppRoot "venv"
$BinDir = Join-Path $AppRoot "bin"

Write-Host "[GenomeAI] repo_root=$RepoRoot"
Write-Host "[GenomeAI] app_root=$AppRoot"

New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# Find python
$Python = $env:GENOMEAI_PYTHON
if ([string]::IsNullOrWhiteSpace($Python)) {
  $Python = "python"
}

try {
  & $Python -c "import sys; print(sys.version)" | Out-Null
} catch {
  throw "Python not found. Install Python 3.11+ and retry (or set GENOMEAI_PYTHON)."
}

if (-Not (Test-Path $VenvDir)) {
  & $Python -m venv $VenvDir
}

$Pip = Join-Path $VenvDir "Scripts\pip.exe"
$PyV = Join-Path $VenvDir "Scripts\python.exe"

& $PyV -m pip install -U pip setuptools wheel | Out-Null

# Install editable from repo with UI extras.
& $Pip install -e "$RepoRoot[ui]" | Out-Null

# Wrapper cmd in app bin
$Wrapper = Join-Path $BinDir "genomeai-agroanimals.cmd"
@"
@echo off
setlocal
set "APP_ROOT=%GENOMEAI_APP_ROOT%"
if "%APP_ROOT%"=="" set "APP_ROOT=%LOCALAPPDATA%\GenomeAI_AgroAnimals"
"%APP_ROOT%\venv\Scripts\genomeai-agroanimals.exe" %*
"@ | Set-Content -Encoding ASCII -Path $Wrapper

# Create Start Menu shortcut (best-effort)
try {
  $StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
  $LnkPath = Join-Path $StartMenu "GenomeAI AgroAnimals.lnk"
  $WScript = New-Object -ComObject WScript.Shell
  $Shortcut = $WScript.CreateShortcut($LnkPath)
  $Shortcut.TargetPath = $Wrapper
  $Shortcut.WorkingDirectory = $RepoRoot
  $Shortcut.WindowStyle = 1
  $Shortcut.Description = "GenomeAI AgroAnimals (local cabinet)"
  $Shortcut.Save()
} catch {
  Write-Host "WARN: could not create Start Menu shortcut: $($_.Exception.Message)"
}

# Create Desktop shortcut (best-effort)
try {
  $DesktopDir = [Environment]::GetFolderPath("Desktop")
  if (-Not [string]::IsNullOrWhiteSpace($DesktopDir)) {
    $DesktopLnk = Join-Path $DesktopDir "GenomeAI AgroAnimals.lnk"
    $WScript2 = New-Object -ComObject WScript.Shell
    $Shortcut2 = $WScript2.CreateShortcut($DesktopLnk)
    $Shortcut2.TargetPath = $Wrapper
    $Shortcut2.WorkingDirectory = $RepoRoot
    $Shortcut2.WindowStyle = 1
    $Shortcut2.Description = "GenomeAI AgroAnimals (local cabinet)"
    $Shortcut2.Save()
  }
} catch {
  Write-Host "WARN: could not create Desktop shortcut: $($_.Exception.Message)"
}

Write-Host "OK: installed"
Write-Host "Run: $Wrapper --open-browser"
