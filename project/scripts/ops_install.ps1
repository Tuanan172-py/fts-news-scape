# ops_install.ps1 - Cai dat control plane van hanh tu chu (ADR 0012) tren Windows.
#
#   powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register -Start -Shortcut
#   powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Uninstall
#
# Mo hinh van hanh: may mo thi daemon chay; may ngu/tat thi moi thu dung, bai nam cho.
# Khong tat sleep, khong auto-logon, khong loai tru Defender.
#
# Task chay duoi tai khoan nguoi dung, chi khi dang dang nhap: agy doc thong tin dang nhap
# trong ho so nguoi dung, Session 0 cua Windows service khong thay duoc.
# Hai trigger: luc dang nhap + lap moi 5 phut. Khoa mot the hien cua daemon chan chay trung,
# nen trigger lap dong vai watchdog khoi dong lai daemon da chet.

param(
    [switch]$Register,
    [switch]$Start,
    [switch]$Shortcut,
    [switch]$Uninstall,
    [string]$Venv = "C:\venvs\news-scape"
)

$ErrorActionPreference = "Stop"
$TaskName = "news-scape-ops"
$WatchdogTask = "news-scape-ops-watchdog"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonW = Join-Path $Venv "Scripts\pythonw.exe"
$Python = Join-Path $Venv "Scripts\python.exe"
$DaemonScript = Join-Path $ProjectDir "scripts\ops_daemon.py"
$ConsoleScript = Join-Path $ProjectDir "scripts\ops_console.py"
$LinkPath = Join-Path ([Environment]::GetFolderPath("Programs")) "News-Scape Ops.lnk"

if ($Uninstall) {
    foreach ($t in @($TaskName, $WatchdogTask)) {
        if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $t -Confirm:$false
            Write-Host "Da go task $t."
        }
    }
    if (Test-Path $LinkPath) { Remove-Item $LinkPath -Force; Write-Host "Da go loi tat." }
    exit 0
}

if ($Register) {
    if (-not (Test-Path $PythonW)) { throw "Khong thay $PythonW" }
    $action = New-ScheduledTaskAction -Execute $PythonW -Argument "`"$DaemonScript`" run" -WorkingDirectory $ProjectDir
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
    $watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -Priority 4
    # Mac dinh Task Scheduler chay o priority 7: CPU va I/O uu tien thap, va moi tien trinh
    # con (article_run, --finish) thua huong. Do duoc: mot luot sensor 1,3 s khi chay tay
    # thanh 40-400 s trong task. Priority 4 la muc binh thuong.
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atLogon, $watchdog) `
        -Settings $settings -Principal $principal -Force `
        -Description "News-Scape ops_daemon: sensor 100 bai, workflow dot, heartbeat, Telegram (ADR 0012)" | Out-Null
    Write-Host "Da dang ky task $TaskName (dang nhap + khoi dong lai moi 5 phut)."

    # Watchdog doc lap: bao Telegram khi daemon chet trong luc may mo. May ngu thi task
    # nay cung khong chay, nen khong bao dong gia khi gap may.
    $wdAction = New-ScheduledTaskAction -Execute $PythonW -Argument "`"$DaemonScript`" watchdog" -WorkingDirectory $ProjectDir
    $wdTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
        -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
    $wdSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName $WatchdogTask -Action $wdAction -Trigger $wdTrigger `
        -Settings $wdSettings -Principal $principal -Force `
        -Description "News-Scape ops watchdog: bao khi ops_daemon chet luc may mo (ADR 0012)" | Out-Null
    Write-Host "Da dang ky task $WatchdogTask (moi 5 phut)."
}

if ($Start) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Da khoi dong $TaskName. Kiem tra: python scripts\ops_daemon.py status"
}

if ($Shortcut) {
    $wt = (Get-Command wt.exe -ErrorAction SilentlyContinue).Source
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($LinkPath)
    if ($wt) {
        $lnk.TargetPath = $wt
        $lnk.Arguments = "-w _quake --title `"news-scape ops`" `"$Python`" `"$ConsoleScript`""
    } else {
        $lnk.TargetPath = $Python
        $lnk.Arguments = "`"$ConsoleScript`""
    }
    $lnk.WorkingDirectory = $ProjectDir
    $lnk.Hotkey = "CTRL+ALT+O"
    $lnk.Description = "Bang dieu khien van hanh News-Scape"
    $lnk.Save()
    Write-Host "Da tao loi tat $LinkPath voi phim Ctrl+Alt+O (quake window: Win+`` de an/hien)."
}
