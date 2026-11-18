<#
.SYNOPSIS
  Empaqueta dist\ para un release: instalador NSIS, zip portable y sumas SHA-256.

.PARAMETER Version
  Versión SemVer del release (por ejemplo 1.0.0).

.PARAMETER Msys2Root
  Carpeta de MSYS2; makensis sale del paquete mingw-w64-x86_64-nsis.

.EXAMPLE
  .\winbuild\build.ps1
  .\winbuild\package.ps1 -Version 1.0.0     # deja los ficheros en winbuild\out\release
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,
    [string]$Msys2Root = $(if ($env:MSYS2_ROOT) { $env:MSYS2_ROOT } else { 'C:\msys64' })
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $repoRoot 'dist'
$out = Join-Path $PSScriptRoot 'out\release'
$makensis = Join-Path $Msys2Root 'mingw64\bin\makensis.exe'

foreach ($f in 'Xming.exe', 'XLaunch.exe', 'COPYING.txt') {
    if (-not (Test-Path (Join-Path $dist $f))) {
        throw "Falta dist\$f. Ejecuta antes winbuild\build.ps1."
    }
}
if (-not (Test-Path $makensis)) {
    throw "makensis no encontrado. Instálalo con: $Msys2Root\usr\bin\pacman.exe -S mingw-w64-x86_64-nsis"
}

if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
$base = "Xming-fork-$Version"

# Instalador
$setup = Join-Path $out "$base-setup.exe"
$nsi = Join-Path $PSScriptRoot 'installer\xming.nsi'
& $makensis -V2 "/DVERSION=$Version" "/DDIST=$dist" "/DOUTFILE=$setup" $nsi
if ($LASTEXITCODE -ne 0) { throw "makensis falló (código $LASTEXITCODE)" }

# Portable: el contenido de dist\ dentro de una carpeta con el nombre del release.
# xkb\compiled se queda fuera: en Windows los mapas compilados van a %TEMP%.
$stage = Join-Path $out $base
Copy-Item -Recurse $dist $stage
Remove-Item -Recurse -Force (Join-Path $stage 'xkb\compiled') -ErrorAction SilentlyContinue
$zip = Join-Path $out "$base-portable.zip"
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Remove-Item -Recurse -Force $stage

# Sumas de comprobación
$sums = Get-ChildItem $out -File | Where-Object Name -ne 'SHA256SUMS.txt' | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $_.Name
}
Set-Content -Path (Join-Path $out 'SHA256SUMS.txt') -Value $sums -Encoding ascii

Get-ChildItem $out | Select-Object Name, Length
