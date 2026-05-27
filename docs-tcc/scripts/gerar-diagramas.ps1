$ErrorActionPreference = "Stop"
$ImagesRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\images")).Path
$Cfg = Join-Path $ImagesRoot "mermaid-config.json"

$Diagrams = @(
    @{
        Input  = "figure1-polyglot-ecommerce.mmd"
        Output = "figure1-polyglot-ecommerce.png"
        Width  = 1400
    },
    @{
        Input  = "figure3-nosql-data-models.mmd"
        Output = "figure3-nosql-data-models.png"
        Width  = 1400
    },
    @{
        Input  = "figure4-import-algorithm.mmd"
        Output = "figure4-import-algorithm.png"
        Width  = 1600
    }
)

Push-Location $ImagesRoot
try {
    foreach ($d in $Diagrams) {
        Write-Host "Gerando $($d.Output) ..."
        npx -y @mermaid-js/mermaid-cli@11.4.0 `
            -c $Cfg `
            -b white `
            -w $d.Width `
            -s 2 `
            -i $d.Input `
            -o $d.Output
    }
}
finally {
    Pop-Location
}

Write-Host "Diagramas atualizados em $ImagesRoot"
