$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $buildDirectory = 'build/winsor-sensitivity-20261029'
    $jobName = 'bp_single_factor_report_winsor_sensitivity_20261029'
    New-Item -ItemType Directory -Force -Path $buildDirectory | Out-Null
    foreach ($pass in 1..2) {
        & xelatex -interaction=nonstopmode -halt-on-error -file-line-error "-output-directory=$buildDirectory" "-jobname=$jobName" main.tex *> "$buildDirectory/compile-$pass.txt"
        if ($LASTEXITCODE -ne 0) { throw "XeLaTeX failed; see $buildDirectory/compile-$pass.txt" }
    }
    Copy-Item -LiteralPath "$buildDirectory/$jobName.pdf" -Destination "$jobName.pdf" -Force
    Write-Output "Compiled $jobName.pdf; original PDFs retained."
} finally {
    Pop-Location
}
