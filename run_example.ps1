#Requires -Version 5.1
<#
.SYNOPSIS
  E-commerce running example: Docker stack + dry-run + real import.

.DESCRIPTION
  Starts PostgreSQL, Redis, MongoDB, Cassandra and Neo4j via docker compose,
  waits for Cassandra (slowest), then runs Polyglot Import CSV on
  data/ecommerce/ecommerce_join.csv with data/ecommerce/import_config.json.

  Prerequisites: Docker Desktop, Python 3.9+ with pip install -e ".[dev]"
#>
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

$Csv = "data/ecommerce/ecommerce_join.csv"
$Config = "data/ecommerce/import_config.json"

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    throw "Python not found. Install Python 3.9+ and run: pip install -e `".[dev]`""
}

function Wait-TcpPort {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port,
        [int]$TimeoutSeconds = 120,
        [string]$Label = "service"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    Write-Host "Waiting for $Label on ${HostName}:$Port (up to ${TimeoutSeconds}s)..."
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $async = $client.BeginConnect($HostName, $Port, $null, $null)
            $ok = $async.AsyncWaitHandle.WaitOne(2000, $false)
            if ($ok -and $client.Connected) {
                $client.Close()
                Write-Host "  $Label is ready."
                return
            }
            $client.Close()
        } catch {
            # retry
        }
        Start-Sleep -Seconds 3
    }
    throw "Timeout waiting for $Label on port $Port."
}

function Invoke-Import {
    param(
        [string]$Python,
        [switch]$DryRun
    )
    $args = @(
        "-m", "polyglotimportcsv",
        $Csv,
        "--config", $Config
    )
    if ($DryRun) {
        $args += "--dry-run"
    } else {
        $args += "--create-schema"
    }
    & $Python @args
    if ($LASTEXITCODE -ne 0) { throw "polyglotimportcsv failed (exit $LASTEXITCODE)." }
}

$python = Get-PythonCommand

Write-Host "=== Polyglot Import CSV — running example ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker not found. Install Docker Desktop and ensure 'docker compose' works."
}

Write-Host "Starting Docker services (docker compose up -d)..."
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Wait-TcpPort -Port 5432 -Label "PostgreSQL"
Wait-TcpPort -Port 6379 -Label "Redis"
Wait-TcpPort -Port 27017 -Label "MongoDB"
Wait-TcpPort -Port 9042 -TimeoutSeconds 180 -Label "Cassandra"
Wait-TcpPort -Port 7687 -Label "Neo4j"

Write-Host ""
Write-Host "=== Dry-run (no database connections) ===" -ForegroundColor Cyan
Invoke-Import -Python $python -DryRun

Write-Host ""
Write-Host "=== Real import (--create-schema) ===" -ForegroundColor Cyan
Invoke-Import -Python $python

Write-Host ""
Write-Host "Done. Inspect databases or re-run with --dry-run only:" -ForegroundColor Green
Write-Host "  $python -m polyglotimportcsv $Csv --config $Config --dry-run"
