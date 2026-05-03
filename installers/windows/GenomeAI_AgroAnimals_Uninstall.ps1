$ErrorActionPreference = "Stop"

$AppRoot = $env:GENOMEAI_APP_ROOT
if ([string]::IsNullOrWhiteSpace($AppRoot)) {
  $AppRoot = Join-Path $env:LOCALAPPDATA "GenomeAI_AgroAnimals"
}

Write-Host "[GenomeAI] removing $AppRoot"

try {
  $StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
  $LnkPath = Join-Path $StartMenu "GenomeAI AgroAnimals.lnk"
  if (Test-Path $LnkPath) { Remove-Item -Force $LnkPath }
} catch {
  Write-Host "WARN: could not remove shortcut: $($_.Exception.Message)"
}

try {
  $DesktopDir = [Environment]::GetFolderPath("Desktop")
  if (-Not [string]::IsNullOrWhiteSpace($DesktopDir)) {
    $DesktopLnk = Join-Path $DesktopDir "GenomeAI AgroAnimals.lnk"
    if (Test-Path $DesktopLnk) { Remove-Item -Force $DesktopLnk }
  }
} catch {
  Write-Host "WARN: could not remove Desktop shortcut: $($_.Exception.Message)"
}

if (Test-Path $AppRoot) {
  Remove-Item -Recurse -Force $AppRoot
}

Write-Host "OK: uninstalled"