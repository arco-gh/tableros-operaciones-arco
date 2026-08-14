# Despliegue en Azure App Service — Tablero Ejecutivo ARCO

Guía autocontenida. No requiere haber leído las otras.

> **¿Prefiere hacerlo sin línea de comandos?** Todo lo que aquí se hace con
> Azure CLI puede ejecutarse desde `portal.azure.com`. La guía equivalente,
> pantalla por pantalla, es **[DEPLOY_AZURE_PORTAL.md](DEPLOY_AZURE_PORTAL.md)**.
> El resultado es idéntico; sólo cambia el medio.

**Resultado esperado:** el tablero publicado en `https://tablero.arco.mx`, con
inicio de sesión de cuenta ARCO, y una carpeta de red donde Contraloría deposita
los Excel cada mes sin que nadie tenga que volver a desplegar nada.

**Tiempo estimado:** 90 minutos la primera vez.

---

## Antes de empezar

Necesitas:

- Suscripción de Azure con permiso de **Colaborador** sobre un grupo de recursos.
- Azure CLI instalado (`az --version` debe responder).
- El proyecto en un repositorio Git privado, o al menos la carpeta local.
- Los cuatro archivos Excel del mes de corte.

Un dato que conviene tener claro desde el inicio: **el tablero no es un sitio
estático**. Azure App Service va a ejecutar un proceso de Python permanentemente,
no a servir archivos. Por eso importan los ajustes de arranque y de sesión que
vienen más abajo.

---

## Paso 1 — Crear la infraestructura

```bash
az login
az account set --subscription "<nombre-o-id-de-la-suscripcion>"

az group create \
  --name rg-arco-tablero \
  --location southcentralus
```

`southcentralus` es la región de Azure más cercana al norte de México y da la
mejor latencia para Tijuana, Mexicali, Culiacán y Saltillo. Si ARCO ya tiene
región estándar corporativa, usa esa.

```bash
az appservice plan create \
  --name plan-arco-tablero \
  --resource-group rg-arco-tablero \
  --sku B1 \
  --is-linux
```

Sobre el tamaño: **B1** (1 core, 1.75 GB) es suficiente para el volumen actual —
diez plazas, unos 5 mil registros de cartera y las series de tráfico. Cuesta del
orden de 55 USD mensuales. Si más adelante se suma el histórico mensual del P&L
o crece mucho el número de usuarios simultáneos, subir a **B2** es un solo
comando y no requiere redesplegar.

```bash
az webapp create \
  --name arco-tablero \
  --resource-group rg-arco-tablero \
  --plan plan-arco-tablero \
  --runtime "PYTHON:3.12"
```

El nombre `arco-tablero` debe ser único en todo `azurewebsites.net`. Si está
tomado, usa algo como `arco-tablero-mx`.

---

## Paso 2 — Crear el almacenamiento de los datos

Esta es la pieza que permite actualizar el mes sin volver a desplegar. Los Excel
**no** viven dentro de la aplicación: viven en un recurso de Azure Files que se
monta como si fuera una carpeta local.

```bash
az storage account create \
  --name stgarcotablero \
  --resource-group rg-arco-tablero \
  --sku Standard_LRS \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false

az storage share-rm create \
  --resource-group rg-arco-tablero \
  --storage-account stgarcotablero \
  --name datos-arco \
  --quota 5
```

Obtener la clave de acceso:

```bash
az storage account keys list \
  --account-name stgarcotablero \
  --resource-group rg-arco-tablero \
  --query "[0].value" -o tsv
```

Montarlo en la aplicación:

```bash
az webapp config storage-account add \
  --resource-group rg-arco-tablero \
  --name arco-tablero \
  --custom-id datos-arco \
  --storage-type AzureFiles \
  --account-name stgarcotablero \
  --share-name datos-arco \
  --access-key "<la-clave-obtenida-arriba>" \
  --mount-path /mnt/arco-datos
```

---

## Paso 3 — Configurar el arranque

```bash
az webapp config set \
  --name arco-tablero \
  --resource-group rg-arco-tablero \
  --startup-file "bash /home/site/wwwroot/deploy/startup.sh"

az webapp config appsettings set \
  --name arco-tablero \
  --resource-group rg-arco-tablero \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    ARCO_DATA_DIR=/mnt/arco-datos \
    ARCO_ENTORNO="Azure" \
    WEBSITES_CONTAINER_START_TIME_LIMIT=600 \
    PYTHONUNBUFFERED=1
```

Qué hace cada ajuste, porque varios son la diferencia entre que funcione y que
no:

| Ajuste | Para qué |
|---|---|
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | Instala `requirements.txt` durante el despliegue. Sin esto, la app arranca sin Streamlit. |
| `ARCO_DATA_DIR` | Apunta el tablero al montaje de Azure Files en lugar de a `data/raw` dentro del código. |
| `ARCO_ENTORNO` | Etiqueta que aparece en el encabezado. Importa si vas a operar también un ambiente interno. |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | La primera lectura de los Excel tarda más que el límite predeterminado; sin esto Azure da el arranque por fallido. |

---

## Paso 4 — Publicar el código

**Opción A — Despliegue directo desde la carpeta:**

```bash
cd arco_dashboard
zip -r tablero.zip . -x "data/*" ".venv/*" ".git/*" "*.pyc" "__pycache__/*"

az webapp deploy \
  --name arco-tablero \
  --resource-group rg-arco-tablero \
  --src-path tablero.zip \
  --type zip
```

**Opción B — Desde Azure DevOps o GitHub** (recomendada para el largo plazo,
porque cada actualización del tablero queda trazada):

```bash
az webapp deployment source config \
  --name arco-tablero \
  --resource-group rg-arco-tablero \
  --repo-url https://dev.azure.com/arco/Tablero/_git/tablero \
  --branch main \
  --manual-integration
```

El `.gitignore` del proyecto ya excluye `data/`, de modo que **los Excel nunca
viajan en el repositorio**. Contienen estados de resultados por plaza y el
detalle de deudores con nombre y saldo.

---

## Paso 5 — Ajustes que evitan fallas típicas

```bash
# El WebSocket de Streamlit necesita que el usuario regrese siempre a la
# misma instancia. Sin esto, al cambiar de pestaña se pierde la sesión.
az webapp update \
  --name arco-tablero --resource-group rg-arco-tablero \
  --client-affinity-enabled true

# Evita el arranque en frío: sin esto, el primer usuario del día espera
# 30 segundos mientras Azure levanta el proceso.
az webapp config set \
  --name arco-tablero --resource-group rg-arco-tablero \
  --always-on true

# Información financiera: sólo https.
az webapp update \
  --name arco-tablero --resource-group rg-arco-tablero \
  --https-only true
```

Verificar que responde:

```bash
curl https://arco-tablero.azurewebsites.net/_stcore/health
```

Debe devolver `ok`. Si no, ver la sección de diagnóstico.

---

## Paso 6 — Subir los datos del mes

Desde el portal: **Cuenta de almacenamiento → Recursos compartidos de archivos →
datos-arco → Cargar**, y subir los cuatro Excel.

Desde la línea de comandos:

```bash
for archivo in RF_Comparativos_por_Plaza_JUNIO_2026__SV_.xlsx \
               AFLUENCIASPLAZAS_11.xlsx \
               Historico_detalle_Clientes_Valores_Jun_26_-_Operacion.xlsm \
               OCUP_JUN26.xlsx; do
  az storage file upload \
    --account-name stgarcotablero \
    --share-name datos-arco \
    --source "data/raw/$archivo"
done
```

Reiniciar para que tome los archivos:

```bash
az webapp restart --name arco-tablero --resource-group rg-arco-tablero
```

Abrir `https://arco-tablero.azurewebsites.net` y confirmar que el encabezado
muestra **Junio 2026** en *Última actualización de datos*.

---

## Paso 7 — Control de acceso con Entra ID

Sin este paso, cualquiera con la URL ve los estados de resultados de ARCO.

En el portal de Azure:

1. App Service `arco-tablero` → **Autenticación** → *Agregar proveedor de
   identidades*.
2. Proveedor: **Microsoft**.
3. Tipo de cuenta: *Sólo el directorio actual* (cuentas de ARCO únicamente).
4. Acción cuando no hay autenticación: **Requerir autenticación** →
   *HTTP 302 Redirect*.
5. Guardar.

A partir de ahí entra cualquier cuenta de ARCO. **Para limitarlo a la Dirección
y las gerencias**, que es lo apropiado para este contenido:

1. Entra ID → **Aplicaciones empresariales** → buscar `arco-tablero`.
2. **Propiedades** → *¿Se requiere asignación de usuarios?* → **Sí**.
3. **Usuarios y grupos** → *Agregar usuario o grupo* → seleccionar el grupo
   correspondiente (por ejemplo `GRP-Tablero-Directivo`).

Conviene crear el grupo en Entra ID antes, con los miembros de Dirección
General, direcciones funcionales y gerencias de plaza.

---

## Paso 8 — Dominio propio y certificado

```bash
# 1. En el DNS de ARCO, crear:
#      CNAME  tablero  ->  arco-tablero.azurewebsites.net
#      TXT    asuid.tablero  ->  <id-de-verificacion>
#
# El id se obtiene con:
az webapp show --name arco-tablero --resource-group rg-arco-tablero \
  --query customDomainVerificationId -o tsv

# 2. Registrar el dominio
az webapp config hostname add \
  --webapp-name arco-tablero \
  --resource-group rg-arco-tablero \
  --hostname tablero.arco.mx

# 3. Certificado administrado y gratuito de Azure
az webapp config ssl create \
  --resource-group rg-arco-tablero \
  --name arco-tablero \
  --hostname tablero.arco.mx

# 4. Enlazarlo (el thumbprint lo devuelve el comando anterior)
az webapp config ssl bind \
  --resource-group rg-arco-tablero \
  --name arco-tablero \
  --certificate-thumbprint "<thumbprint>" \
  --ssl-type SNI
```

El certificado administrado se renueva solo. No hay que ponerle recordatorio a
nadie.

---

## Actualización mensual

1. **Contraloría y Operaciones suben los cuatro archivos** al recurso compartido
   `datos-arco`, conservando el patrón de nombre. El mes puede seguir en el
   nombre:

   | Archivo | Patrón que debe cumplir |
   |---|---|
   | Estado de resultados | `RF_Comparativos*.xlsx` |
   | Afluencia y aforo | `AFLUENCIA*.xlsx` |
   | Cartera | `Historico_detalle_Clientes*.xlsm` |
   | Ocupación | `OCUP*.xlsx` |

2. **Mover los del mes anterior** a una subcarpeta `historico/` dentro del mismo
   recurso. Si quedan dos archivos que cumplen el mismo patrón, el tablero toma
   el más reciente por fecha, lo cual funciona pero deja margen a la ambigüedad.

3. **Entrar al tablero y pulsar "Recargar fuentes"** en la barra lateral.
   Confirmar que el encabezado muestra el mes nuevo.

### Que Contraloría no tenga que usar el portal de Azure

Montar el recurso compartido como unidad de red en los equipos autorizados. Así
copiar los archivos es igual que copiarlos a cualquier carpeta:

```powershell
# En el equipo de quien deposita los archivos, una sola vez.
# El comando exacto lo genera el portal en:
#   Cuenta de almacenamiento > Recursos compartidos > datos-arco > Conectar
net use Z: \\stgarcotablero.file.core.windows.net\datos-arco `
  /user:localhost\stgarcotablero "<clave-de-la-cuenta>" /persistent:yes
```

Requiere que el puerto 445 esté abierto de salida, cosa que algunos proveedores
de internet bloquean. Si es el caso, la alternativa es Azure Storage Explorer,
que funciona sobre https.

### Automatizarlo

Si los archivos ya viven en SharePoint, programar una sincronización nocturna
hacia el recurso compartido con `rclone` o Azure Data Factory. Es lo que evita
que el tablero se quede atrasado porque alguien salió de vacaciones.

---

## Operación

### Comprobar disponibilidad

```
https://tablero.arco.mx/_stcore/health
```

Devuelve `ok`. Es la ruta adecuada para configurar una prueba de disponibilidad
en Application Insights.

### Ver bitácoras

```bash
az webapp log tail --name arco-tablero --resource-group rg-arco-tablero
```

Para dejarlas habilitadas de forma permanente:

```bash
az webapp log config \
  --name arco-tablero --resource-group rg-arco-tablero \
  --application-logging filesystem --level information
```

### Actualizar el código del tablero

```bash
cd arco_dashboard
git pull
zip -r tablero.zip . -x "data/*" ".venv/*" ".git/*" "*.pyc" "__pycache__/*"
az webapp deploy --name arco-tablero --resource-group rg-arco-tablero \
  --src-path tablero.zip --type zip
```

Los datos no se tocan: viven en el montaje, no en el paquete.

### Escalar

```bash
az appservice plan update \
  --name plan-arco-tablero --resource-group rg-arco-tablero --sku B2
```

---

## Diagnóstico

| Síntoma | Causa | Solución |
|---|---|---|
| Se queda en *"Connecting..."* | Falta afinidad de sesión | `az webapp update --client-affinity-enabled true` |
| *Application Error* al abrir | El arranque excedió el límite | Verificar `WEBSITES_CONTAINER_START_TIME_LIMIT=600` y revisar `log tail` |
| *ModuleNotFoundError: streamlit* | No se instalaron dependencias | Verificar `SCM_DO_BUILD_DURING_DEPLOYMENT=true` y volver a desplegar |
| *No se encontró el archivo de 'financiero'* | El montaje no está o el nombre no cumple el patrón | `az webapp config storage-account list` y comparar nombres |
| Muestra el mes anterior | Caché vigente | Pulsar **Recargar fuentes**; si persiste, `az webapp restart` |
| Primer acceso del día muy lento | Arranque en frío | Verificar `--always-on true` |
| El montaje aparece vacío | La clave de la cuenta se rotó | Volver a ejecutar `storage-account add` con la clave nueva |

---

## Costos aproximados

| Concepto | Mensual (USD) |
|---|---|
| App Service Plan B1 Linux | ~55 |
| Cuenta de almacenamiento (5 GB, Standard_LRS) | ~1 |
| Certificado administrado | 0 |
| Entra ID (incluido en Microsoft 365) | 0 |
| **Total** | **~56** |

Con B2, del orden de 110 USD mensuales.

---

## Lista de verificación

- [ ] `https://tablero.arco.mx/_stcore/health` devuelve `ok`
- [ ] El certificado es válido y el dominio resuelve
- [ ] Al abrir sin sesión, redirige al inicio de sesión de ARCO
- [ ] Sólo el grupo autorizado puede entrar
- [ ] Los filtros responden (confirma que el WebSocket funciona)
- [ ] El encabezado muestra el mes correcto
- [ ] `always-on` y `client-affinity` están activos
- [ ] Contraloría tiene acceso al recurso compartido y sabe usarlo
- [ ] Hay un responsable nombrado para la actualización mensual
- [ ] Los Excel están respaldados fuera de Azure Files
- [ ] La clave de la cuenta de almacenamiento está en Key Vault, no en un correo
