param(
    [string]$WslDistro = "Ubuntu-24.04",
    [string]$WslUser = "smirn",
    [string]$WslProjectDir = "chemtg"
)

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Smart Build ChemTG Bot via PowerShell" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

$WinBuildDir = Join-Path $env:USERPROFILE "ChemTG_Build_Env"

Write-Host "1. Syncing files from WSL to $WinBuildDir..." -ForegroundColor Yellow
if (-not (Test-Path $WinBuildDir)) {
    New-Item -ItemType Directory -Force -Path $WinBuildDir | Out-Null
}

# Превращаем путь C:\Users\smirn\... в формат WSL: /mnt/c/Users/smirn/...
$WslWinBuildDir = "/mnt/c/" + ($WinBuildDir.Substring(3) -replace "\\", "/")

Write-Host "   Packing project in WSL and transferring..." -ForegroundColor Gray
wsl -d $WslDistro -u $WslUser -- bash -c "cd /home/$WslUser/$WslProjectDir && tar -cf '$WslWinBuildDir/temp_project.tar' --exclude='.git' --exclude='venv_linux' --exclude='venv_win' --exclude='.venv' --exclude='build' --exclude='dist' --exclude='Output' --exclude='__pycache__' --exclude='.pytest_cache' ."

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to pack files in WSL." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit $LASTEXITCODE
}

Write-Host "   Extracting files in Windows..." -ForegroundColor Gray
tar -xf "$WinBuildDir\temp_project.tar" -C "$WinBuildDir"
Remove-Item "$WinBuildDir\temp_project.tar" -Force

Set-Location $WinBuildDir

Write-Host ""
Write-Host "2. Checking Windows virtual environment (venv_win)..." -ForegroundColor Yellow
if (-not (Test-Path "venv_win\Scripts\activate.ps1")) {
    Write-Host "   Directory venv_win not found. Creating from scratch..." -ForegroundColor Gray
    python -m venv venv_win
} else {
    Write-Host "   Virtual environment venv_win already exists." -ForegroundColor Green
}

Write-Host ""
Write-Host "3. Checking Python dependencies..." -ForegroundColor Yellow
$PythonExe = Join-Path $PWD "venv_win\Scripts\python.exe"
$PipExe = Join-Path $PWD "venv_win\Scripts\pip.exe"
$PyInstallerExe = Join-Path $PWD "venv_win\Scripts\pyinstaller.exe"

& $PythonExe -m pip install --upgrade pip | Out-Null
& $PipExe install -r core\requirements.txt | Out-Null
& $PipExe install -r updater\requirements.txt | Out-Null
& $PipExe install pyinstaller | Out-Null

Write-Host ""
Write-Host "4. Running PyInstaller (building EXE)..." -ForegroundColor Yellow
& $PyInstallerExe ChemTG_Bot.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] EXE build failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit $LASTEXITCODE
}
Write-Host "   EXE successfully built." -ForegroundColor Green

Write-Host ""
Write-Host "5. Creating Installer (Inno Setup)..." -ForegroundColor Yellow

$ISCC = ""
$PathsToTry = @(
    "C:\Program Files (x86)\Inno Setup 6\iscc.exe",
    "C:\Program Files\Inno Setup 6\iscc.exe",
    "C:\Program Files (x86)\Inno Setup 7\iscc.exe",
    "C:\Program Files\Inno Setup 7\iscc.exe"
)

foreach ($Path in $PathsToTry) {
    if (Test-Path $Path) {
        $ISCC = $Path
        break
    }
}

if ($ISCC -ne "") {
    & $ISCC installer.iss
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create Inno Setup installer." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit $LASTEXITCODE
    }
    Write-Host "   Installer successfully created in: $WinBuildDir\Output\" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "6. Copying installer back to WSL..." -ForegroundColor Yellow
    
    # Копируем готовый .exe обратно в WSL через /mnt/c
    $InstallerPath = Join-Path $PWD "Output\ChemTG_Bot_Installer.exe"
    $WslInstallerPath = "/mnt/c/" + ($InstallerPath.Substring(3) -replace "\\", "/")
    
    wsl -d $WslDistro -u $WslUser -- bash -c "mkdir -p /home/$WslUser/$WslProjectDir/Output && cp '$WslInstallerPath' /home/$WslUser/$WslProjectDir/Output/ChemTG_Bot_Installer.exe"
    
    Write-Host "   Installer successfully copied to your project folder (Output/ChemTG_Bot_Installer.exe)!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[WARNING] Inno Setup compiler not found." -ForegroundColor DarkYellow
    Write-Host "Please download and install Inno Setup from: https://jrsoftware.org/isdl.php" -ForegroundColor Gray
    Write-Host "Run this script again after installation." -ForegroundColor Gray
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "ALL DONE!" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Read-Host "Press Enter to exit"
