<#
    Registra el Tablero Ejecutivo ARCO como servicio de Windows usando NSSM.

    Ejecutar en PowerShell como Administrador desde la carpeta del proyecto:
        .\deploy\instalar_servicio_windows.ps1

    Requiere NSSM (https://nssm.cc) disponible en el PATH. Sin un servicio, el
    tablero se detiene al cerrar la sesión de quien lo inició.
#>

param(
    [string]$RutaProyecto = (Resolve-Path "$PSScriptRoot\.."),
    [string]$RutaDatos    = "\\fileserver\ARCO\Tablero\data\raw",
    [int]   $Puerto       = 8501,
    [string]$Servicio     = "ArcoTablero"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RutaProyecto ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No se encontró el entorno virtual en $python. Cree primero .venv e instale requirements.txt."
}

Write-Host "Registrando el servicio $Servicio..."
nssm install $Servicio $python "-m streamlit run `"$RutaProyecto\app.py`" --server.port=$Puerto --server.address=127.0.0.1 --server.headless=true --server.fileWatcherType=none"

nssm set $Servicio AppDirectory   $RutaProyecto
nssm set $Servicio AppEnvironmentExtra "ARCO_DATA_DIR=$RutaDatos"
nssm set $Servicio DisplayName    "Tablero Ejecutivo ARCO"
nssm set $Servicio Description    "Tablero de seguimiento y diagnostico de ARCO (Streamlit)"
nssm set $Servicio Start          SERVICE_AUTO_START
nssm set $Servicio AppStdout      (Join-Path $RutaProyecto "logs\tablero.log")
nssm set $Servicio AppStderr      (Join-Path $RutaProyecto "logs\tablero-error.log")
nssm set $Servicio AppRotateFiles 1

New-Item -ItemType Directory -Force -Path (Join-Path $RutaProyecto "logs") | Out-Null

Write-Host "Iniciando el servicio..."
nssm start $Servicio

Write-Host ""
Write-Host "Listo. El tablero responde en http://127.0.0.1:$Puerto"
Write-Host "Publique ese puerto con IIS usando deploy\web.config."
