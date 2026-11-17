# Changelog

Todos los cambios relevantes de este fork se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). La numeración parte de la
versión original de Xming (6.9.0.31); el historial anterior está en `ChangeLog` y
`programs/Xserver/hw/xwin/ChangeLog`.

## [Unreleased]

### Added
- Build reproducible nativo en Windows con MSYS2 + mingw-w64 (`winbuild/setup.ps1`,
  `winbuild/build.ps1`), sin depender de Cygwin ni de compilación cruzada desde Linux.

### Changed
- La copia de trabajo usa siempre finales de línea LF (`.gitattributes`), necesario para que
  imake y make funcionen en Windows.

### Fixed
- El bootstrap de imake no compilaba fuera de compilación cruzada y no podía usar `/tmp` en
  Windows.

## [6.9.0.31] - 2007

### Added
- Copia sin modificar del código fuente de Xming 6.9.0.31 publicada en SourceForge.
