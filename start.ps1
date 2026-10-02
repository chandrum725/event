<#
.SYNOPSIS
    Eventora – Windows launcher: brings MySQL up (only when it is down) and
    then starts the Flask server that serves the website and the admin panel.

.DESCRIPTION
    This machine has no MySQL *Windows service* (installing one needs an
    elevated shell), so MySQL used to be started by hand – forget it once and
    "python app.py" answers "database: unavailable" (HTTP 503) while the pages
    themselves keep working. This script removes that trap:

        up      (default) start MySQL if port 3306 is closed, then run Flask
        db                only make sure MySQL is running
        status            show whether MySQL / the website are up + DB check
        stop              stop the website and shut MySQL down cleanly

    MySQL is read from C:\ProgramData\MySQL\MySQL Server 8.4\my.ini.

.PARAMETER Action
    up (default), db, status or stop.

.PARAMETER Port
    Port for the Flask server (default 5000).

.PARAMETER DebugMode
    Pass --debug to Flask (auto-reload + tracebacks in the browser).

.EXAMPLE
    .\start.ps1
    Website  http://127.0.0.1:5000/      Admin  http://127.0.0.1:5000/admin/login

.EXAMPLE
    .\start.ps1 db        # just the database
    .\start.ps1 status    # is everything healthy?
    .\start.ps1 stop      # shut everything down

.NOTES
    Ctrl+C stops Flask only – MySQL keeps running (that is intentional, it is
    what makes the next start instant). Use ".\start.ps1 stop" for both.
#>
[CmdletBinding()]
param(
    [ValidateSet('up', 'db', 'status', 'stop')]
    [string]$Action = 'up',
    [int]$Port = 5000,
    [switch]$DebugMode
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------- #
#  Locations – change these if MySQL or the project ever moves.
# --------------------------------------------------------------------------- #
$AppDir    = $PSScriptRoot
$DotEnv    = Join-Path $AppDir '.env'
$MysqlIni  = 'C:\ProgramData\MySQL\MySQL Server 8.4\my.ini'
$MysqlLog  = 'C:\ProgramData\MySQL\MySQL Server 8.4\Data\mysql-error.log'
$DefaultDbPort = 3306

function Write-Step { param([string]$Message) Write-Host "[..] $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "[ok] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[!]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[x]  $Message" -ForegroundColor Red }

# --------------------------------------------------------------------------- #
#  Small helpers
# --------------------------------------------------------------------------- #

# Reads a ".env" file into a hash table (KEY = VALUE, "#" comments, quotes
# stripped). Used for the MySQL user/password so nothing has to be typed twice.
function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }

    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith('#')) { continue }
        $split = $text.IndexOf('=')
        if ($split -lt 1) { continue }
        $key   = $text.Substring(0, $split).Trim()
        $value = $text.Substring($split + 1).Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }
    return $values
}

# True when something accepts TCP connections on the port already.
function Test-Port {
    param([int]$Number, [string]$Address = '127.0.0.1')

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync($Address, $Number)
        if (-not $connect.Wait(500)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

# First mysqld.exe we can find: PATH, the MySQL 8.4 install, then any version.
function Find-Mysqld {
    $fromPath = Get-Command mysqld.exe -ErrorAction SilentlyContinue
    if ($fromPath -and (Test-Path -LiteralPath $fromPath.Source)) { return $fromPath.Source }

    $standard = 'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe'
    if (Test-Path -LiteralPath $standard) { return $standard }

    $found = Get-ChildItem 'C:\Program Files\MySQL\*\bin\mysqld.exe' -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

# Project virtual environment first, then the interpreter on PATH.
# The venv normally sits next to this script, but in this workspace it lives one
# folder up (at the workspace root), so both places are checked.
function Find-Python {
    $roots = @($AppDir, (Split-Path -Path $AppDir -Parent))
    foreach ($root in $roots) {
        foreach ($relative in @('.venv\Scripts\python.exe', 'venv\Scripts\python.exe')) {
            $candidate = Join-Path $root $relative
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    foreach ($name in @('python.exe', 'py.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

$Settings      = Read-DotEnv -Path $DotEnv
$MysqlPort     = if ($Settings['MYSQL_PORT']) { [int]$Settings['MYSQL_PORT'] } else { $DefaultDbPort }
$MysqlUser     = if ($Settings['MYSQL_USER']) { $Settings['MYSQL_USER'] } else { 'root' }
$MysqlPassword = $Settings['MYSQL_PASSWORD']
$Python        = Find-Python

# --------------------------------------------------------------------------- #
#  MySQL
# --------------------------------------------------------------------------- #
function Start-MySql {
    if (Test-Port -Number $MysqlPort) {
        Write-Ok "MySQL is already listening on 127.0.0.1:$MysqlPort"
        return $true
    }

    $mysqld = Find-Mysqld
    if (-not $mysqld) {
        Write-Fail 'mysqld.exe was not found. Install MySQL Server 8.4, then run'
        Write-Fail 'this script again (or start MySQL from Windows Services).'
        return $false
    }

    $arguments = @()
    if (Test-Path -LiteralPath $MysqlIni) {
        # The path contains spaces, so mysqld itself needs the quotes.
        $arguments += "--defaults-file=`"$MysqlIni`""
    } else {
        Write-Warn "No defaults file at $MysqlIni - starting MySQL with its own defaults."
    }

    Write-Step "Starting MySQL ($mysqld)"
    Start-Process -FilePath $mysqld -ArgumentList $arguments -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        if (Test-Port -Number $MysqlPort) {
            Write-Ok "MySQL is up on 127.0.0.1:$MysqlPort"
            return $true
        }
    }

    Write-Fail "MySQL did not answer on port $MysqlPort within 45 seconds."
    if (Test-Path -LiteralPath $MysqlLog) { Write-Fail "Check the log: $MysqlLog" }
    return $false
}

function Stop-MySql {
    if (-not (Test-Port -Number $MysqlPort)) {
        Write-Ok 'MySQL is not running.'
        return
    }

    $mysqld = Find-Mysqld
    $admin  = if ($mysqld) { Join-Path (Split-Path $mysqld) 'mysqladmin.exe' } else { $null }
    if (-not $admin -or -not (Test-Path -LiteralPath $admin)) {
        Write-Warn 'mysqladmin.exe was not found - stopping the MySQL process instead.'
        Get-Process mysqld -ErrorAction SilentlyContinue | Stop-Process -Force
        Write-Ok 'MySQL stopped.'
        return
    }

    Write-Step 'Asking MySQL to shut down (mysqladmin shutdown)'
    # MYSQL_PWD keeps the password off the command line (and out of the logs).
    $previousPassword = $env:MYSQL_PWD
    $env:MYSQL_PWD = $MysqlPassword
    try {
        & $admin --host=127.0.0.1 "--port=$MysqlPort" "--user=$MysqlUser" shutdown 2>&1 | Out-Null
    } finally {
        $env:MYSQL_PWD = $previousPassword
    }

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-Port -Number $MysqlPort)) { Write-Ok 'MySQL stopped.'; return }
        Start-Sleep -Milliseconds 500
    }
    Write-Warn 'MySQL is still listening - close it from the Task Manager if needed.'
}

# --------------------------------------------------------------------------- #
#  Python / Flask
# --------------------------------------------------------------------------- #
function Test-FlaskDependencies {
    if (-not $Python) { return $false }
    & $Python -c "import flask, pymysql, dotenv" 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Install-FlaskDependencies {
    Write-Step 'Installing the requirements (Flask, PyMySQL, python-dotenv)'
    Push-Location $AppDir
    try {
        & $Python -m pip install -r (Join-Path $AppDir 'requirements.txt')
        if ($LASTEXITCODE -ne 0) {
            Write-Fail 'pip could not install the requirements - check your connection.'
            return $false
        }
    } finally {
        Pop-Location
    }
    return $true
}

# The Flask development server that owns the website port, if any.
function Get-ServerProcess {
    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
                  Select-Object -First 1
    if (-not $connection) { return $null }
    return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
}

function Start-Flask {
    if (-not $Python) {
        Write-Fail 'No Python interpreter was found on PATH. Install Python 3.10+ and retry.'
        return 1
    }

    if (-not (Test-FlaskDependencies)) {
        if (-not (Install-FlaskDependencies)) { return 1 }
    }

    $existing = Get-ServerProcess
    if ($existing) {
        Write-Warn "Port $Port is already used by $($existing.ProcessName) (PID $($existing.Id))."
        Write-Warn 'Stop it first with:  .\start.ps1 stop     (or pick another -Port)'
        return 1
    }

    Push-Location $AppDir
    try {
        & $Python (Join-Path $AppDir 'app.py') check-db
        if ($LASTEXITCODE -ne 0) {
            Write-Warn 'The database is not ready - the pages will load, but uploads and'
            Write-Warn 'the admin panel need MySQL. Start it with:  .\start.ps1 db'
        }

        Write-Host ''
        Write-Ok "Website     : http://127.0.0.1:$Port/"
        Write-Ok "Admin panel : http://127.0.0.1:$Port/admin/login   (not linked from the site)"
        Write-Host '[i]  Ctrl+C stops the server - MySQL keeps running.' -ForegroundColor DarkGray
        Write-Host ''

        $appArguments = @((Join-Path $AppDir 'app.py'), '--port', "$Port")
        if ($DebugMode) { $appArguments += '--debug' }
        & $Python @appArguments
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

function Stop-Flask {
    $process = Get-ServerProcess
    if (-not $process) {
        Write-Ok "Nothing is listening on port $Port."
        return
    }
    Write-Step "Stopping $($process.ProcessName) on port $Port (PID $($process.Id))"
    Stop-Process -Id $process.Id -Force
    Write-Ok 'The Flask server has stopped.'
}

function Show-Status {
    if (Test-Port -Number $MysqlPort) {
        Write-Ok "MySQL        : running on 127.0.0.1:$MysqlPort"
    } else {
        Write-Fail 'MySQL        : not running   (start it with:  .\start.ps1 db)'
    }

    $server = Get-ServerProcess
    if ($server) {
        Write-Ok "Flask server : http://127.0.0.1:$Port/ ($($server.ProcessName), PID $($server.Id))"
    } else {
        Write-Fail 'Flask server : not running   (start it with:  .\start.ps1)'
    }

    if ($Python) {
        Push-Location $AppDir
        try { & $Python (Join-Path $AppDir 'app.py') check-db } finally { Pop-Location }
    } else {
        Write-Fail 'Python       : not found on PATH'
    }

    Write-Host ''
    Write-Host '[i]  MySQL is started on demand by this script. For a real Windows' -ForegroundColor DarkGray
    Write-Host '    service (auto-start, one elevated terminal needed):' -ForegroundColor DarkGray
    Write-Host '      & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe" `' -ForegroundColor DarkGray
    Write-Host "          --install MySQL84 --defaults-file=`"$MysqlIni`"" -ForegroundColor DarkGray
    Write-Host '      Start-Service MySQL84' -ForegroundColor DarkGray
}

# --------------------------------------------------------------------------- #
#  Go
# --------------------------------------------------------------------------- #
switch ($Action) {
    'db' {
        if (-not (Start-MySql)) { exit 1 }
    }
    'stop' {
        Stop-Flask
        Stop-MySql
    }
    'status' {
        Show-Status
    }
    default {
        if (-not (Start-MySql)) {
            Write-Warn 'Starting the website anyway - only the pages will work.'
        }
        exit (Start-Flask)
    }
}
