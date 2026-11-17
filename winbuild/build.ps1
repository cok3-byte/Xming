<#
.SYNOPSIS
  Compila Xming de forma nativa en Windows con MSYS2 (MINGW32) y deja el resultado en dist\.

.PARAMETER Msys2Root
  Carpeta de instalación de MSYS2 (por defecto C:\msys64).

.PARAMETER Jobs
  Trabajos paralelos de make. Por defecto, todos los núcleos lógicos de la máquina.

.PARAMETER Incremental
  Recompila solo lo que cambió, sin distclean ni bootstrap de imake.
  Requiere haber hecho antes un build completo.

.EXAMPLE
  .\winbuild\build.ps1                # build completo con todos los núcleos
  .\winbuild\build.ps1 -Incremental   # iteración rápida tras editar código
  .\winbuild\build.ps1 -Jobs 4        # limitar el uso de CPU
#>
[CmdletBinding()]
param(
    [string]$Msys2Root = $(if ($env:MSYS2_ROOT) { $env:MSYS2_ROOT } else { 'C:\msys64' }),
    [ValidateRange(1, 256)]
    [int]$Jobs = [Environment]::ProcessorCount,
    [switch]$Incremental
)

$ErrorActionPreference = 'Stop'

$bash = Join-Path $Msys2Root 'usr\bin\bash.exe'
if (-not (Test-Path $bash)) {
    throw "MSYS2 no encontrado en $Msys2Root. Ejecuta antes winbuild\setup.ps1."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $PSScriptRoot 'out'
New-Item -ItemType Directory -Force $logDir | Out-Null
$mode = if ($Incremental) { 'incremental' } else { 'world' }
$log = Join-Path $logDir "$mode.log"

# MSYSTEM=MINGW32 pone /mingw32/bin primero en el PATH (gcc de 32 bits)
$env:MSYSTEM = 'MINGW32'
$env:CHERE_INVOKING = '1'

$script = Join-Path $PSScriptRoot 'build.sh'
$scriptUnix = (& (Join-Path $Msys2Root 'usr\bin\cygpath.exe') -u $script).Trim()

Write-Host "Compilando ($mode, $Jobs trabajos; log: $log)..."
$sw = [Diagnostics.Stopwatch]::StartNew()
& $bash -lc "sh '$scriptUnix' $Jobs $mode" 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ("Duración: {0:hh\:mm\:ss}" -f $sw.Elapsed)

if ($code -ne 0) {
    throw "El build falló (código $code). Revisa $log"
}

Write-Host "Build completo. Binarios en $(Join-Path $repoRoot 'dist')"
