#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    $python = "py"
}

& $python -m polyglotimportcsv `
    "data/ecommerce/ecommerce_join.csv" `
    --config "data/ecommerce/import_config.json" `
    --dry-run
