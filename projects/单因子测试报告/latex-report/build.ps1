$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force -Path 'build' | Out-Null
    foreach ($pass in 1..2) {
        & xelatex -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build main.tex *> "build/compile-$pass.txt"
        if ($LASTEXITCODE -ne 0) { throw "XeLaTeX failed; see build/compile-$pass.txt" }
    }
    Copy-Item -LiteralPath 'build/main.pdf' -Destination 'main.pdf' -Force
    Write-Output 'Compiled main.pdf with local XeLaTeX.'
} finally {
    Pop-Location
}
