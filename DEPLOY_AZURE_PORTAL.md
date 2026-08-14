# Despliegue en Azure App Service desde el portal — Tablero Ejecutivo ARCO

Guía autocontenida, sin línea de comandos. Es el equivalente punto por punto de
`DEPLOY_AZURE.md`, ejecutado desde `portal.azure.com`.

**Resultado esperado:** el tablero publicado en `https://tablero.arco.mx`, con
inicio de sesión de cuenta ARCO, y una carpeta donde Contraloría deposita los
Excel cada mes sin que nadie tenga que volver a desplegar nada.

**Tiempo estimado:** 2 horas la primera vez.

> **Sobre los nombres de las opciones.** Microsoft reorganiza el portal con
> cierta frecuencia; en particular, la hoja *Configuración* de App Service se
> dividió en *Configuración* y *Variables de entorno*. Cuando un nombre no
> coincida exactamente con lo que ve en pantalla, la guía describe también qué
> hace la opción para que pueda ubicarla. El buscador superior del portal
> resuelve casi cualquier duda de navegación.

---

## Antes de empezar

Necesita:

- Cuenta de Azure con rol **Colaborador** sobre una suscripción o grupo de recursos.
- Permiso en Entra ID para registrar aplicaciones (paso 8). Si no lo tiene,
  ese paso lo ejecuta el administrador del tenant.
- El proyecto comprimido en un `.zip`, o publicado en Azure DevOps / GitHub.
- Los cuatro archivos Excel del mes de corte.

Un dato que conviene tener claro: **el tablero no es un sitio estático**. Azure
va a ejecutar un proceso de Python permanentemente, no a servir archivos. Por
eso importan los ajustes de arranque y de sesión del paso 6.

---

## Paso 1 — Crear el grupo de recursos

1. Entrar a `portal.azure.com`.
2. Buscar **Grupos de recursos** en la barra superior.
3. **+ Crear**.
4. Llenar:
   - Suscripción: la de ARCO
   - Nombre: `rg-arco-tablero`
   - Región: **Centro-sur de EE. UU.** (South Central US)
5. **Revisar y crear** → **Crear**.

Sobre la región: Centro-sur de EE. UU. es la más cercana al norte de México y da
la mejor latencia para Tijuana, Mexicali, Culiacán y Saltillo. Si ARCO ya tiene
una región corporativa estándar, use esa.

---

## Paso 2 — Crear el App Service

1. **Crear un recurso** → buscar **Aplicación web** → **Crear**.
2. Pestaña **Aspectos básicos**:

   | Campo | Valor |
   |---|---|
   | Grupo de recursos | `rg-arco-tablero` |
   | Nombre | `arco-tablero` |
   | Publicar | **Código** |
   | Pila del entorno de ejecución | **Python 3.12** |
   | Sistema operativo | **Linux** |
   | Región | Centro-sur de EE. UU. |

3. En **Plan de precios**, pulsar *Crear nuevo*:
   - Nombre: `plan-arco-tablero`
   - Pulsar **Explorar todos los planes** → pestaña **Desarrollo/pruebas** →
     **B1** (1 núcleo, 1.75 GB).

   B1 es suficiente para el volumen actual: diez plazas, unos 5 mil registros de
   cartera y las series de tráfico. Cuesta del orden de 55 USD mensuales. Subir
   a B2 después es un cambio de un minuto y no requiere volver a desplegar.

4. Pestaña **Supervisión**: dejar Application Insights en **Sí** si quiere
   métricas y alertas de disponibilidad. Es opcional pero recomendable.
5. **Revisar y crear** → **Crear**. Tarda un par de minutos.

Si el nombre `arco-tablero` está tomado —debe ser único en todo
`azurewebsites.net`— use `arco-tablero-mx` o similar.

---

## Paso 3 — Crear el almacenamiento de los datos

Esta es la pieza que permite actualizar el mes sin volver a desplegar. Los Excel
**no** viven dentro de la aplicación: viven en un recurso de Azure Files que se
monta como si fuera una carpeta local del servidor.

### 3.1 Cuenta de almacenamiento

1. **Crear un recurso** → buscar **Cuenta de almacenamiento** → **Crear**.
2. Pestaña **Aspectos básicos**:

   | Campo | Valor |
   |---|---|
   | Grupo de recursos | `rg-arco-tablero` |
   | Nombre | `stgarcotablero` (sólo minúsculas y números) |
   | Región | la misma del App Service |
   | Rendimiento | Estándar |
   | Redundancia | **LRS** (redundancia local) |

3. Pestaña **Avanzado**: desmarcar **Permitir el acceso público de blobs** y
   dejar la versión mínima de TLS en **1.2**.
4. **Revisar y crear** → **Crear**.

### 3.2 Recurso compartido de archivos

1. Entrar a la cuenta `stgarcotablero`.
2. Menú izquierdo → **Almacenamiento de datos** → **Recursos compartidos de archivos**.
3. **+ Recurso compartido de archivos**:
   - Nombre: `datos-arco`
   - Nivel de acceso: **Optimizado para transacciones**
4. **Crear**.

### 3.3 Copiar la clave de acceso

1. En la misma cuenta, menú izquierdo → **Seguridad y redes** → **Claves de acceso**.
2. En **key1**, pulsar **Mostrar** y copiar la **Clave**.
3. Guardarla temporalmente; se usa en el paso siguiente.

Guárdela después en el gestor de credenciales de TI o en Key Vault. **No la
envíe por correo.**

---

## Paso 4 — Montar el almacenamiento en la aplicación

1. Entrar al App Service `arco-tablero`.
2. Menú izquierdo → **Configuración** → **Configuración** (en algunas versiones
   del portal aparece directamente como *Path mappings* o *Asignaciones de ruta
   de acceso*).
3. Pestaña **Asignaciones de ruta de acceso**.
4. **+ Nuevo montaje de Azure Storage**:

   | Campo | Valor |
   |---|---|
   | Nombre | `datos-arco` |
   | Tipo de configuración | Básico |
   | Cuenta de almacenamiento | `stgarcotablero` |
   | Tipo de almacenamiento | **Azure Files** |
   | Nombre del recurso compartido | `datos-arco` |
   | Ruta de acceso de montaje | `/mnt/arco-datos` |

5. **Aceptar** → **Guardar**.

---

## Paso 5 — Cargar los archivos del mes

1. Volver a la cuenta `stgarcotablero`.
2. **Recursos compartidos de archivos** → `datos-arco`.
3. **Cargar** y seleccionar los cuatro archivos:
   - `RF_Comparativos_por_Plaza_JUNIO_2026__SV_.xlsx`
   - `AFLUENCIASPLAZAS_11.xlsx`
   - `Historico_detalle_Clientes_Valores_Jun_26_-_Operacion.xlsm`
   - `OCUP_JUN26.xlsx`
4. Crear también un directorio `historico` con **+ Agregar directorio**. Ahí se
   moverán los archivos de meses anteriores.

---

## Paso 6 — Configurar el arranque y las variables

### 6.1 Comando de inicio

1. App Service `arco-tablero` → **Configuración** → pestaña **Configuración general**.
2. Campo **Comando de inicio**:

   ```
   bash /home/site/wwwroot/deploy/startup.sh
   ```

3. En la misma pestaña, ajustar:

   | Opción | Valor | Para qué |
   |---|---|---|
   | **Siempre activado** (Always on) | **Activado** | Evita que el primer usuario del día espere 30 segundos mientras Azure levanta el proceso |
   | **Afinidad de sesión ARR** | **Activado** | El WebSocket de Streamlit necesita que el usuario regrese siempre a la misma instancia |
   | **HTTP versión** | 1.1 | |
   | **WebSockets** | **Activado** | |

4. **Guardar**.

### 6.2 Variables de entorno

1. Menú izquierdo → **Configuración** → **Variables de entorno** (en versiones
   anteriores: *Configuración* → pestaña *Configuración de la aplicación*).
2. Pestaña **Configuración de la aplicación** → **+ Agregar**, una por una:

   | Nombre | Valor |
   |---|---|
   | `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
   | `ARCO_DATA_DIR` | `/mnt/arco-datos` |
   | `ARCO_ENTORNO` | `Azure` |
   | `WEBSITES_CONTAINER_START_TIME_LIMIT` | `600` |
   | `PYTHONUNBUFFERED` | `1` |

3. **Aplicar** → **Confirmar**.

Qué hace cada una, porque varias son la diferencia entre que funcione y que no:

- `SCM_DO_BUILD_DURING_DEPLOYMENT` instala `requirements.txt` durante el
  despliegue. Sin esto, la aplicación arranca sin Streamlit instalado.
- `ARCO_DATA_DIR` apunta el tablero al montaje en lugar de a `data/raw` dentro
  del código. Es lo que separa datos de aplicación.
- `ARCO_ENTORNO` etiqueta la instancia en el encabezado. Importa si también va a
  operar un ambiente interno: sin la etiqueta, dos instancias con datos de meses
  distintos son indistinguibles.
- `WEBSITES_CONTAINER_START_TIME_LIMIT` amplía el tiempo de arranque. La primera
  lectura de los Excel excede el límite predeterminado y Azure daría el
  despliegue por fallido.

### 6.3 Sólo HTTPS

1. Menú izquierdo → **Configuración** → **Configuración general**.
2. **Solo HTTPS**: **Activado**.
3. **Guardar**.

---

## Paso 7 — Publicar el código

Aquí está la única diferencia real frente a la línea de comandos: **el portal no
tiene un botón para subir un `.zip` directamente**. Hay dos caminos, ambos desde
el navegador.

### Opción A — Repositorio (recomendada)

Deja trazada cada actualización del tablero y permite volver atrás.

1. App Service → **Implementación** → **Centro de implementación**.
2. Origen: **Azure Repos** o **GitHub**.
3. Autorizar, y seleccionar organización, proyecto, repositorio y rama `main`.
4. Proveedor de compilación: **App Service Build Service**.
5. **Guardar**. Azure despliega y volverá a hacerlo con cada `push`.

El `.gitignore` del proyecto excluye `data/`, de modo que **los Excel nunca
viajan en el repositorio**. Contienen estados de resultados por plaza y el
detalle de deudores con nombre y saldo.

### Opción B — Arrastrar el ZIP en la consola web

Sin repositorio, usando la herramienta de administración avanzada. Sigue siendo
navegador, no línea de comandos.

1. Comprimir la carpeta del proyecto en `tablero.zip`, **excluyendo** `data/`,
   `.venv/`, `.git/` y `__pycache__/`.
2. App Service → **Herramientas de desarrollo** → **Herramientas avanzadas** →
   **Ir** (abre Kudu en una pestaña nueva).
3. En Kudu: menú **Tools** → **Zip Push Deploy**.
4. Arrastrar `tablero.zip` sobre la ventana. Se descomprime y despliega solo.

### Verificar

Abrir:

```
https://arco-tablero.azurewebsites.net/_stcore/health
```

Debe mostrar `ok`. Si no, ver la sección de diagnóstico.

Luego abrir `https://arco-tablero.azurewebsites.net` y confirmar que el
encabezado muestra **Junio 2026** en *Última actualización de datos*.

---

## Paso 8 — Control de acceso con Entra ID

Sin este paso, cualquiera con la URL ve los estados de resultados de ARCO.

### 8.1 Exigir inicio de sesión

1. App Service → **Configuración** → **Autenticación**.
2. **Agregar proveedor de identidades**.
3. Configurar:

   | Campo | Valor |
   |---|---|
   | Proveedor de identidades | **Microsoft** |
   | Tipo de cliente | Aplicación web |
   | Tipos de cuenta admitidos | **Solo el directorio actual** |
   | Restringir el acceso | **Requerir autenticación** |
   | Solicitudes no autenticadas | **HTTP 302 Redireccionamiento encontrado** |

4. **Agregar**.

Abrir el tablero en una ventana privada: debe redirigir al inicio de sesión de
ARCO.

### 8.2 Limitarlo a la Dirección y las gerencias

Con lo anterior entra cualquier cuenta de ARCO, incluido todo el personal. Para
restringirlo a quien corresponde:

1. Buscar **Microsoft Entra ID** en el portal.
2. **Grupos** → **+ Nuevo grupo**:
   - Tipo: Seguridad
   - Nombre: `GRP-Tablero-Directivo`
   - Agregar como miembros a Dirección General, direcciones funcionales y
     gerencias de plaza.
3. **Aplicaciones empresariales** → buscar `arco-tablero`.
4. **Propiedades** → *¿Se requiere asignación de usuarios?* → **Sí** → **Guardar**.
5. **Usuarios y grupos** → **+ Agregar usuario o grupo** → seleccionar
   `GRP-Tablero-Directivo` → **Asignar**.

A partir de ahí, quien no esté en el grupo recibe un mensaje de acceso denegado
aunque tenga cuenta de ARCO.

---

## Paso 9 — Dominio propio y certificado

### 9.1 Obtener el identificador de verificación

1. App Service → **Configuración** → **Dominios personalizados**.
2. Copiar el valor de **Id. de verificación de dominio personalizado**.

### 9.2 Registros DNS

En el DNS de ARCO (con el proveedor del dominio), crear:

| Tipo | Nombre | Valor |
|---|---|---|
| CNAME | `tablero` | `arco-tablero.azurewebsites.net` |
| TXT | `asuid.tablero` | el identificador copiado arriba |

La propagación puede tardar hasta una hora.

### 9.3 Agregar el dominio

1. **Dominios personalizados** → **+ Agregar dominio personalizado**.
2. Origen del certificado: **Certificado administrado de App Service**
   (gratuito y de renovación automática).
3. Dominio: `tablero.arco.mx`. Tipo de registro: CNAME.
4. **Validar** → **Agregar**.

Azure emite el certificado y lo enlaza. No hay que ponerle recordatorio a nadie
para renovarlo.

---

## Actualización mensual

1. **Contraloría y Operaciones cargan los cuatro archivos** en el recurso
   compartido `datos-arco`, conservando el patrón de nombre. El mes puede seguir
   formando parte del nombre:

   | Archivo | Patrón que debe cumplir |
   |---|---|
   | Estado de resultados | `RF_Comparativos*.xlsx` |
   | Afluencia y aforo | `AFLUENCIA*.xlsx` |
   | Cartera | `Historico_detalle_Clientes*.xlsm` |
   | Ocupación | `OCUP*.xlsx` |

2. **Mover los del mes anterior** a la carpeta `historico`. Si quedan dos
   archivos que cumplen el mismo patrón, el tablero toma el más reciente por
   fecha: funciona, pero deja margen a la ambigüedad.

3. **Entrar al tablero y pulsar "Recargar fuentes"** en la barra lateral.
   Confirmar que el encabezado muestra el mes nuevo.

### Que Contraloría no tenga que entrar al portal de Azure

Dos alternativas, ninguna requiere darles acceso a la suscripción:

**Azure Storage Explorer** (recomendada). Aplicación gratuita de escritorio que
funciona sobre https. Se instala una vez, se conecta con la clave del recurso
compartido, y luego se usa arrastrando archivos como en el Explorador de
Windows.

**Unidad de red.** Desde la cuenta de almacenamiento → *Recursos compartidos* →
`datos-arco` → **Conectar**, el portal genera el comando de conexión listo para
copiar. Queda como unidad `Z:` en el equipo. Requiere que el puerto 445 esté
abierto de salida, cosa que varios proveedores de internet bloquean; si es el
caso, use Storage Explorer.

### Automatizarlo

Si los archivos ya viven en SharePoint, programar una sincronización nocturna
hacia el recurso compartido con Azure Data Factory o `rclone`. Es lo que evita
que el tablero se quede atrasado porque alguien salió de vacaciones.

---

## Operación desde el portal

| Necesidad | Dónde |
|---|---|
| Ver si está vivo | Abrir `https://tablero.arco.mx/_stcore/health` → debe decir `ok` |
| Bitácoras en vivo | App Service → **Supervisión** → **Flujo de registro** |
| Reiniciar | App Service → barra superior → **Reiniciar** |
| Cambiar tamaño | App Service → **Escalar verticalmente** → elegir plan |
| Métricas de uso | App Service → **Supervisión** → **Métricas** |
| Alerta de caída | Application Insights → **Disponibilidad** → prueba estándar contra `/_stcore/health` |
| Consola del servidor | **Herramientas de desarrollo** → **SSH** |

### Actualizar el código del tablero

- Con repositorio: hacer `push` a `main`; Azure despliega solo. El avance se ve
  en **Centro de implementación** → **Registros**.
- Con ZIP: repetir el paso 7, opción B.

En ambos casos los datos no se tocan: viven en el montaje, no en el paquete.

---

## Diagnóstico

| Síntoma | Causa | Solución en el portal |
|---|---|---|
| Se queda en *"Connecting..."* | Falta afinidad de sesión | Configuración general → **Afinidad de sesión ARR** → Activado |
| *Application Error* al abrir | El arranque excedió el límite | Verificar `WEBSITES_CONTAINER_START_TIME_LIMIT=600` en Variables de entorno y revisar el Flujo de registro |
| *ModuleNotFoundError: streamlit* | No se instalaron dependencias | Verificar `SCM_DO_BUILD_DURING_DEPLOYMENT=true` y volver a desplegar |
| *No se encontró el archivo de 'financiero'* | El montaje no está o el nombre no cumple el patrón | Configuración → Asignaciones de ruta de acceso; y revisar nombres en el recurso compartido |
| Muestra el mes anterior | Caché vigente | Pulsar **Recargar fuentes**; si persiste, **Reiniciar** |
| Primer acceso del día muy lento | Arranque en frío | Configuración general → **Siempre activado** → Activado |
| El montaje aparece vacío | La clave de la cuenta se rotó | Rehacer el paso 4 con la clave nueva |
| Acceso denegado con cuenta de ARCO | Falta asignación al grupo | Entra ID → Aplicaciones empresariales → Usuarios y grupos |

---

## Costos aproximados

| Concepto | Mensual (USD) |
|---|---|
| App Service Plan B1 Linux | ~55 |
| Cuenta de almacenamiento (5 GB, LRS) | ~1 |
| Certificado administrado | 0 |
| Entra ID (incluido en Microsoft 365) | 0 |
| Application Insights (volumen bajo) | 0 a 5 |
| **Total** | **~56 a 61** |

Con B2, del orden de 110 USD mensuales. Conviene revisar los precios vigentes en
la calculadora de Azure, ya que cambian por región y por acuerdo comercial.

---

## Lista de verificación

- [ ] `https://tablero.arco.mx/_stcore/health` responde `ok`
- [ ] El certificado es válido y el dominio resuelve
- [ ] Al abrir en ventana privada, redirige al inicio de sesión de ARCO
- [ ] Una cuenta de ARCO fuera del grupo recibe acceso denegado
- [ ] Los filtros responden (confirma que el WebSocket funciona)
- [ ] El encabezado muestra el mes correcto
- [ ] **Siempre activado** y **Afinidad de sesión ARR** están activados
- [ ] Contraloría tiene Storage Explorer configurado y sabe usarlo
- [ ] Hay un responsable nombrado para la actualización mensual
- [ ] Los Excel están respaldados fuera de Azure Files
- [ ] La clave de la cuenta de almacenamiento está en Key Vault o en el gestor de
      credenciales de TI, no en un correo
