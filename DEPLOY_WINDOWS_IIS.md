# Despliegue en Windows Server con IIS — Tablero Ejecutivo ARCO

Guía autocontenida. No requiere haber leído las otras.

**Resultado esperado:** el tablero publicado en `https://tablero.arco.local`
dentro de la red de ARCO, arrancando solo con el servidor, y con una carpeta
compartida donde Contraloría deposita los Excel cada mes.

**Tiempo estimado:** 2 horas la primera vez.

---

## Antes de empezar

Necesitas:

- Windows Server 2019 o superior, con acceso de Administrador.
- Rol de **IIS** instalado.
- Permiso para crear una cuenta de servicio en el dominio.
- Certificado TLS de ARCO para el nombre que se va a publicar.
- Los cuatro archivos Excel del mes de corte.

### Cómo funciona esto, en corto

El tablero **no es un sitio estático**. IIS por sí solo no puede servirlo: hay
que ejecutar un proceso de Python que escucha en un puerto local, y usar IIS
únicamente como puerta de entrada.

```
Navegador → IIS (443, certificado, autenticación) → 127.0.0.1:8501 → Streamlit
```

Tres piezas, entonces:

| Pieza | Cómo se resuelve aquí |
|---|---|
| Proceso Streamlit | Python en un entorno virtual |
| Supervisor que lo mantenga vivo | NSSM, como servicio de Windows |
| Puerta de entrada con https | IIS con URL Rewrite y ARR |

---

## Paso 1 — Instalar los requisitos en el servidor

### 1.1 Python

Descargar Python 3.12 de python.org e instalarlo **para todos los usuarios**,
marcando *Add Python to PATH*.

```powershell
python --version
```

### 1.2 Módulos de IIS

Descargar e instalar, en este orden:

1. **URL Rewrite** — https://www.iis.net/downloads/microsoft/url-rewrite
2. **Application Request Routing (ARR) 3.0** — https://www.iis.net/downloads/microsoft/application-request-routing

Después, activar el proxy (paso que se olvida con frecuencia y hace que todo
falle con error 404):

1. Abrir **IIS Manager**.
2. Seleccionar el **nodo del servidor** (no un sitio).
3. Abrir **Application Request Routing Cache**.
4. En el panel derecho, **Server Proxy Settings**.
5. Marcar **Enable proxy** y aplicar.

### 1.3 NSSM

Descargar de https://nssm.cc/download, descomprimir, y copiar
`win64\nssm.exe` a `C:\Windows\System32` para tenerlo en el PATH.

```powershell
nssm version
```

---

## Paso 2 — Instalar el proyecto

```powershell
mkdir C:\Aplicaciones\ArcoTablero
cd C:\Aplicaciones\ArcoTablero

# Desde el repositorio
git clone <url-del-repositorio> .
# O bien: descomprimir arco_dashboard.zip aquí

python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Prueba rápida, aún sin servicio ni IIS:

```powershell
streamlit run app.py --server.port 8501
```

Abrir `http://localhost:8501` en el servidor. Si el tablero carga y los filtros
responden, el proyecto está bien instalado. Cerrar con `Ctrl+C`.

---

## Paso 3 — Preparar la carpeta de datos

Los Excel **no** viven dentro de la carpeta del proyecto. Van en un recurso
compartido, para que actualizarlos no requiera tocar el servidor de aplicación
ni redesplegar nada.

En el servidor de archivos:

```powershell
New-Item -ItemType Directory -Path "D:\ARCO\Tablero\data\raw" -Force
New-Item -ItemType Directory -Path "D:\ARCO\Tablero\data\historico" -Force

New-SmbShare -Name "TableroDatos" -Path "D:\ARCO\Tablero" `
  -FullAccess "ARCO\GRP-Tablero-Carga" `
  -ReadAccess "ARCO\svc_tablero"
```

Los permisos importan y no son simétricos:

| Quién | Permiso | Por qué |
|---|---|---|
| `GRP-Tablero-Carga` (Contraloría, Operaciones) | Lectura y escritura | Depositan los archivos cada mes |
| `svc_tablero` (cuenta de servicio) | **Sólo lectura** | El tablero nunca modifica los originales; la restricción lo refuerza en la infraestructura |

Copiar los cuatro Excel a `D:\ARCO\Tablero\data\raw`.

Si el servidor de aplicación es el mismo que el de archivos, la ruta local
(`D:\ARCO\Tablero\data\raw`) funciona igual y evita complicaciones de permisos
de red.

---

## Paso 4 — Crear la cuenta de servicio

En Active Directory, crear `ARCO\svc_tablero`:

- Contraseña que no expira.
- Sin derecho de inicio de sesión interactivo.
- Permiso de lectura sobre `\\fileserver\TableroDatos`.
- Permiso de lectura y ejecución sobre `C:\Aplicaciones\ArcoTablero`.

Una cuenta de dominio es necesaria si la carpeta de datos está en un recurso de
red: `Local System` no puede alcanzarlo.

---

## Paso 5 — Registrar el servicio de Windows

Sin un servicio, el tablero se detiene cuando quien lo inició cierra su sesión.

```powershell
cd C:\Aplicaciones\ArcoTablero

.\deploy\instalar_servicio_windows.ps1 `
    -RutaDatos "\\fileserver\TableroDatos\data\raw" `
    -Puerto 8501
```

Asignarle la cuenta de dominio y la etiqueta de ambiente:

```powershell
nssm set ArcoTablero ObjectName "ARCO\svc_tablero" "<contraseña>"
nssm set ArcoTablero AppEnvironmentExtra `
    "ARCO_DATA_DIR=\\fileserver\TableroDatos\data\raw" `
    "ARCO_ENTORNO=Servidor interno"
nssm restart ArcoTablero
```

Verificar:

```powershell
Get-Service ArcoTablero
Invoke-WebRequest http://127.0.0.1:8501/_stcore/health -UseBasicParsing
```

Debe devolver `ok`. Si no, revisar `C:\Aplicaciones\ArcoTablero\logs\tablero-error.log`.

---

## Paso 6 — Publicar con IIS

### 6.1 Crear el sitio

```powershell
New-Item -ItemType Directory -Path "C:\inetpub\arco-tablero" -Force

Import-Module WebAdministration
New-Website -Name "ArcoTablero" `
  -PhysicalPath "C:\inetpub\arco-tablero" `
  -Port 80 -HostHeader "tablero.arco.local"
```

### 6.2 Colocar la configuración del proxy

```powershell
Copy-Item C:\Aplicaciones\ArcoTablero\deploy\web.config `
          C:\inetpub\arco-tablero\web.config
```

Ese archivo contiene dos reglas. La primera es la que hace que el tablero
funcione de verdad:

```xml
<rule name="Streamlit WebSocket" stopProcessing="true">
  <match url="^_stcore/stream" />
  <action type="Rewrite" url="http://127.0.0.1:8501/{R:0}" />
</rule>
```

**Streamlit mantiene un WebSocket abierto con el navegador.** Sin esta regla, el
tablero carga la pantalla completa pero se queda en *"Connecting..."* y no
responde a ningún filtro. Es la falla más común de estos despliegues y desde
fuera parece un problema de la aplicación cuando es del proxy.

### 6.3 Certificado y https

Importar el certificado de ARCO en **Certificados del equipo local → Personal**,
y agregar el binding:

```powershell
New-WebBinding -Name "ArcoTablero" -Protocol https -Port 443 `
  -HostHeader "tablero.arco.local" -SslFlags 1

$cert = Get-ChildItem Cert:\LocalMachine\My |
        Where-Object { $_.Subject -match "tablero.arco" }

New-Item -Path "IIS:\SslBindings\!443!tablero.arco.local" -Value $cert -SSLFlags 1
```

Forzar https agregando una regla al inicio de `<rules>` en el `web.config`:

```xml
<rule name="Forzar HTTPS" stopProcessing="true">
  <match url="(.*)" />
  <conditions>
    <add input="{HTTPS}" pattern="off" />
  </conditions>
  <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
</rule>
```

### 6.4 DNS

En el DNS interno de ARCO, crear un registro A:

```
tablero.arco.local  →  <IP del servidor>
```

---

## Paso 7 — Control de acceso

El tablero no trae autenticación propia, a propósito: se resuelve en IIS, que es
donde ARCO ya administra identidades. Reimplementarla en la aplicación sería
duplicar la responsabilidad y hacerla peor.

### Opción recomendada — Autenticación de Windows

Los usuarios entran con su sesión de dominio, sin escribir contraseña.

```powershell
Set-WebConfigurationProperty -Filter "/system.webServer/security/authentication/windowsAuthentication" `
  -Name Enabled -Value $true -PSPath "IIS:\Sites\ArcoTablero"

Set-WebConfigurationProperty -Filter "/system.webServer/security/authentication/anonymousAuthentication" `
  -Name Enabled -Value $false -PSPath "IIS:\Sites\ArcoTablero"
```

Para limitarlo a un grupo, agregar al `web.config` dentro de
`<system.webServer>`:

```xml
<security>
  <authorization>
    <remove users="*" roles="" verbs="" />
    <add accessType="Allow" roles="ARCO\GRP-Tablero-Directivo" />
  </authorization>
</security>
```

### Restricción adicional por IP

Complementaria, útil si el servidor tiene alguna exposición:

```xml
<security>
  <ipSecurity allowUnlisted="false">
    <add ipAddress="10.10.0.0" subnetMask="255.255.0.0" allowed="true" />
  </ipSecurity>
</security>
```

### Acceso desde fuera de la oficina

Publicarlo por **VPN**. No exponer el servidor directamente a Internet: contiene
estados de resultados por plaza y el detalle de deudores con nombre y saldo.

---

## Actualización mensual

1. **Contraloría y Operaciones copian los cuatro archivos** a
   `\\fileserver\TableroDatos\data\raw`, conservando el patrón de nombre. El mes
   puede seguir formando parte del nombre:

   | Archivo | Patrón que debe cumplir |
   |---|---|
   | Estado de resultados | `RF_Comparativos*.xlsx` |
   | Afluencia y aforo | `AFLUENCIA*.xlsx` |
   | Cartera | `Historico_detalle_Clientes*.xlsm` |
   | Ocupación | `OCUP*.xlsx` |

2. **Mover los del mes anterior** a `data\historico\`. Si quedan dos archivos que
   cumplen el mismo patrón, el tablero toma el más reciente por fecha, lo cual
   funciona pero deja margen a la ambigüedad.

3. **Validar antes de publicar el dato:**

   ```powershell
   cd C:\Aplicaciones\ArcoTablero
   .\.venv\Scripts\activate
   $env:ARCO_DATA_DIR = "\\fileserver\TableroDatos\data\raw"
   python scripts\validar_fuentes.py
   ```

   Debe terminar en `Conciliación correcta.` Si no concilia, el problema está en
   los datos y hay que resolverlo antes de que alguien los vea.

4. **Entrar al tablero y pulsar "Recargar fuentes"** en la barra lateral.
   Confirmar que el encabezado muestra el mes nuevo.

### Automatizar el paso 3

Tarea programada que corre la validación al detectar archivos nuevos y avisa por
correo si falla:

```powershell
$accion = New-ScheduledTaskAction -Execute "C:\Aplicaciones\ArcoTablero\.venv\Scripts\python.exe" `
  -Argument "scripts\validar_fuentes.py" `
  -WorkingDirectory "C:\Aplicaciones\ArcoTablero"

$disparador = New-ScheduledTaskTrigger -Daily -At 7am

Register-ScheduledTask -TaskName "ArcoTablero-Validacion" `
  -Action $accion -Trigger $disparador -User "ARCO\svc_tablero" `
  -Description "Concilia las fuentes del tablero contra el reporte oficial"
```

---

## Operación

### Comandos del servicio

```powershell
Get-Service ArcoTablero
nssm restart ArcoTablero
nssm stop ArcoTablero
nssm start ArcoTablero
nssm edit ArcoTablero      # abre la configuración en ventana
```

### Bitácoras

```
C:\Aplicaciones\ArcoTablero\logs\tablero.log
C:\Aplicaciones\ArcoTablero\logs\tablero-error.log
```

Rotan automáticamente. Las de IIS están en
`C:\inetpub\logs\LogFiles\W3SVC<id>\`.

### Monitoreo

Configurar una prueba contra:

```
https://tablero.arco.local/_stcore/health
```

Debe devolver `ok`.

### Actualizar el código del tablero

```powershell
cd C:\Aplicaciones\ArcoTablero
git pull
.\.venv\Scripts\pip install -r requirements.txt
nssm restart ArcoTablero
```

Los datos no se tocan: viven en el recurso compartido.

---

## Diagnóstico

| Síntoma | Causa | Solución |
|---|---|---|
| Se queda en *"Connecting..."* | Falta la regla del WebSocket, o ARR no tiene el proxy activado | Verificar `web.config` y *Enable proxy* en ARR |
| Error 502.3 | El servicio no está corriendo | `Get-Service ArcoTablero`; revisar `tablero-error.log` |
| Error 404 en todo | ARR sin proxy activado | IIS Manager → nodo servidor → ARR Cache → Server Proxy Settings |
| *No se encontró el archivo de 'financiero'* | `ARCO_DATA_DIR` mal apuntado, o el nombre no cumple el patrón | `nssm get ArcoTablero AppEnvironmentExtra` y comparar nombres |
| *Access denied* sobre el recurso de red | La cuenta de servicio no alcanza el compartido | `nssm set ArcoTablero ObjectName "ARCO\svc_tablero" "<contraseña>"` |
| Muestra el mes anterior | Caché vigente | Pulsar **Recargar fuentes**; si persiste, `nssm restart ArcoTablero` |
| Primera carga lenta (10–20 s) | Lectura inicial de los Excel | Es normal; sólo ocurre tras un reinicio |
| El servicio no arranca al reiniciar el servidor | Tipo de inicio incorrecto | `nssm set ArcoTablero Start SERVICE_AUTO_START` |

---

## Apéndice — Hacerlo sin PowerShell

Los comandos de esta guía tienen equivalente en las herramientas gráficas de
Windows. El resultado es el mismo; use el medio con el que TI se sienta cómodo.

| Paso | Equivalente gráfico |
|---|---|
| Crear la carpeta compartida | Explorador de archivos → clic derecho en la carpeta → *Propiedades* → *Uso compartido* → *Uso compartido avanzado* → *Permisos* |
| Crear la cuenta de servicio | *Usuarios y equipos de Active Directory* → clic derecho en la UO → *Nuevo* → *Usuario* |
| Registrar el servicio | En lugar del script: `nssm install ArcoTablero` abre una ventana donde se capturan ruta, argumentos, cuenta y variables de entorno |
| Cambiar la cuenta del servicio | *Servicios* (`services.msc`) → `ArcoTablero` → *Propiedades* → pestaña *Iniciar sesión* |
| Crear el sitio en IIS | IIS Manager → clic derecho en *Sitios* → *Agregar sitio web* |
| Enlace HTTPS y certificado | IIS Manager → sitio → *Enlaces* → *Agregar* → tipo `https` → seleccionar el certificado |
| Activar el proxy de ARR | IIS Manager → nodo del servidor → *Application Request Routing Cache* → *Server Proxy Settings* → *Enable proxy* |
| Reglas de reescritura | IIS Manager → sitio → *Reescritura de direcciones URL* → *Agregar reglas*. Más simple: copiar el `web.config` incluido, que ya las trae |
| Autenticación de Windows | IIS Manager → sitio → *Autenticación* → habilitar *Autenticación de Windows*, deshabilitar *Autenticación anónima* |
| Autorización por grupo | IIS Manager → sitio → *Reglas de autorización* → *Agregar regla de permiso* → *Roles o grupos de usuarios especificados* |
| Restricción por IP | IIS Manager → sitio → *Restricciones de direcciones IPv4 y de dominio* |
| Registro DNS | *Administrador de DNS* → zona `arco.local` → clic derecho → *Host nuevo (A)* |
| Tarea programada de validación | *Programador de tareas* → *Crear tarea básica* |

La única parte que no tiene equivalente gráfico es la instalación del entorno
virtual de Python (`python -m venv` y `pip install`), que necesariamente se
ejecuta en una consola. Son dos comandos y se corren una sola vez.

---

## Lista de verificación

- [ ] `https://tablero.arco.local/_stcore/health` devuelve `ok`
- [ ] El certificado es válido y el DNS interno resuelve
- [ ] Los filtros responden (confirma que el WebSocket funciona)
- [ ] El encabezado muestra el mes correcto
- [ ] Sólo el grupo autorizado puede entrar
- [ ] El servicio arranca solo tras reiniciar el servidor (probarlo de verdad)
- [ ] La cuenta de servicio alcanza el recurso compartido
- [ ] Contraloría y Operaciones saben dónde depositar los archivos
- [ ] Hay un responsable nombrado para la actualización mensual
- [ ] `validar_fuentes.py` corre programado
- [ ] La carpeta de datos entra en el respaldo del servidor de archivos
- [ ] La contraseña de `svc_tablero` está en el gestor de credenciales de TI
