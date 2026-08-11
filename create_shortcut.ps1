# Creates a Desktop shortcut that launches run_app.bat in this repository.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Campaign Link Hub.lnk"

$runBat = Join-Path $scriptDir "run_app.bat"
if (-not (Test-Path $runBat)) {
    Write-Error "run_app.bat not found in $scriptDir. Create it first or run this script from the project root."
    exit 1
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot "System32\cmd.exe"
$shortcut.Arguments = "/c `"$runBat`""
$shortcut.WorkingDirectory = $scriptDir

$iconPath = Join-Path $scriptDir "static\icon.ico"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}

$shortcut.Save()
Write-Output "Shortcut created: $shortcutPath"
