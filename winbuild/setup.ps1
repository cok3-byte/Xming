<#
.SYNOPSIS
  Prepara MSYS2 y los paquetes necesarios para compilar Xming en Windows.

.PARAMETER Msys2Root
  Carpeta de instalación de MSYS2 (por defecto C:\msys64).
#>
[CmdletBinding()]
param(
    [string]$Msys2Root = $(if ($env:MSYS2_ROOT) { $env:MSYS2_ROOT } else { 'C:\msys64' })
)

$ErrorActionPreference = 'Stop'

$bash = Join-Path $Msys2Root 'usr\bin\bash.exe'

if (-not (Test-Path $bash)) {
    Write-Host "MSYS2 no encontrado en $Msys2Root. Instalando con winget..."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget no está disponible. Instala MSYS2 manualmente desde https://www.msys2.org/'
    }
    winget install --id MSYS2.MSYS2 --exact --accept-package-agreements --source winget
    if (-not (Test-Path $bash)) {
        throw "MSYS2 se instaló pero no aparece en $Msys2Root. Usa -Msys2Root o la variable MSYS2_ROOT."
    }
}

$packagesFile = Join-Path $PSScriptRoot 'msys2-packages.txt'
$packages = Get-Content $packagesFile |
    Where-Object { $_ -and -not $_.StartsWith('#') } |
    ForEach-Object { $_.Trim() }

Write-Host 'Actualizando base de paquetes de MSYS2...'
& $bash -lc 'pacman -Syu --noconfirm' | Out-Host
# pacman puede pedir una segunda pasada tras actualizar el núcleo
& $bash -lc 'pacman -Su --noconfirm' | Out-Host

Write-Host "Instalando: $($packages -join ' ')"
& $bash -lc "pacman -S --needed --noconfirm $($packages -join ' ')" | Out-Host
if ($LASTEXITCODE -ne 0) { throw "pacman falló con código $LASTEXITCODE" }

Write-Host 'Entorno listo. Ejecuta winbuild\build.ps1 para compilar.'
