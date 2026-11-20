# Start vanuit de repositoryroot. Relatieve configuratiepaden gelden vanaf
# de werkdirectory van de aanroeper. Het voorbeeld gebruikt EPSG:28992.
param(
    [string]$BrandlagenConfig = '.\brandlagen.toml',
    [double]$Xmin = 184285,
    [double]$Ymin = 392054,
    [double]$Xmax = 185285,
    [double]$Ymax = 393054
)

$ErrorActionPreference = 'Stop'
$configPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BrandlagenConfig)
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$bounds = @($Xmin, $Ymin, $Xmax, $Ymax) | ForEach-Object { $_.ToString('R', $culture) }
$productionArguments = @(
    'run', '--environment', 'afwateringseenheden', 'afwateringseenheden',
    '--bounds'
) + $bounds + @('--brandlagen-config', $configPath)

Push-Location -LiteralPath $repositoryRoot
try {
    & pixi @productionArguments
    $productionExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $productionExitCode
