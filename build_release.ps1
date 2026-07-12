param(
    [string]$Version = "v1.2"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$specs = @(
    @{ BaseName = "Gestor-Diezmos"; Spec = "Gestor-Diezmos.spec" },
    @{ BaseName = "Sistema-Gestor-Diezmos"; Spec = "Sistema-Gestor-Diezmos.spec" }
)

foreach ($item in $specs) {
    $tempSpec = Join-Path $env:TEMP "$($item.BaseName)-$Version.spec"
    $content = Get-Content $item.Spec -Raw
    # Reemplazar el nombre del ejecutable y la ruta de sheet.py con forward slashes
    $repoSheetPath = Join-Path $repoRoot "sheet.py"
    $repoSheetPath = $repoSheetPath -replace '\\', '/'
    $updated = $content -replace "name='[^']+'", "name='$($item.BaseName)-$Version'"
    $updated = $updated -replace "\['sheet\.py'\]", "['$repoSheetPath']"
    Set-Content -Path $tempSpec -Value $updated -Encoding utf8

    Write-Host "Generando $($item.BaseName)-$Version.exe..."
    py -3 -m PyInstaller --noconfirm --distpath "$repoRoot\dist" "$tempSpec"

    Remove-Item $tempSpec -Force -ErrorAction SilentlyContinue
}

Write-Host "Empaquetado listo para la versión $Version."
