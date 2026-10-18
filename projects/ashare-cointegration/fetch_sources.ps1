$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$sourceDir = Join-Path $PSScriptRoot ".local/sources"
New-Item -ItemType Directory -Force $sourceDir | Out-Null
$downloads = @{
    "StockClassifyUse_stock_live.xls" = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"
    "SwClass.rar" = "https://www.swsresearch.com/swindex/pdf/SwClass2021/SwClass.rar"
}
foreach ($name in $downloads.Keys) {
    $target = Join-Path $sourceDir $name
    if (-not (Test-Path -LiteralPath $target)) {
        Invoke-WebRequest -Uri $downloads[$name] -OutFile "$target.part" -TimeoutSec 120
        Move-Item -LiteralPath "$target.part" -Destination $target
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceDir "SwClassCode_2021.xls"))) {
    tar -xf (Join-Path $sourceDir "SwClass.rar") -C $sourceDir
    if ($LASTEXITCODE -ne 0) { throw "Official catalogue archive extraction failed" }
}
& .\.venv\Scripts\python.exe scripts/probe_sources.py
if ($LASTEXITCODE -ne 0) { throw "BaoStock metadata acquisition failed; completed responses retained" }
