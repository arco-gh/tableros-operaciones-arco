# Tablero Ejecutivo ARCO

Sistema de seguimiento y diagnóstico para ARCO Áreas Comerciales. Convierte los
tres archivos operativos mensuales en un tablero web interactivo que permite
identificar desviaciones, atribuirlas a la unidad que las explica y llegar hasta
el registro que las origina.

---

## Propósito

Fuentes: estado de resultados por plaza, afluencia y aforo, cartera de clientes
y ocupación de área rentable.

El tablero responde ocho preguntas sin abrir el Excel:

1. ¿Cómo cerró el portafolio contra presupuesto y contra el año anterior?
2. ¿Qué indicadores están fuera de objetivo?
3. ¿Qué plazas explican cada desviación y en qué proporción?
4. ¿Qué tendencias trae el negocio más allá del último mes?
5. ¿Dónde hay comportamientos anómalos o deterioro sostenido?
6. ¿Cómo se descompone un KPI por rubro?
7. ¿Qué registros hay detrás del resultado?
8. ¿Qué decisión sugiere el conjunto?

---

## Estructura del proyecto

```
arco_dashboard/
├── app.py                   Orquestación de la interfaz (sin fórmulas de KPI)
├── requirements.txt
├── README.md
├── DEPLOY.md                Índice de despliegue y operación en paralelo
├── DEPLOY_AZURE_PORTAL.md   Guía para Azure desde el portal web
├── DEPLOY_AZURE.md          Guía para Azure con Azure CLI
├── DEPLOY_WINDOWS_IIS.md    Guía para Windows Server con IIS
├── Dockerfile
├── docker-compose.yml
│
├── data/raw/                Archivos fuente — se tratan como READ ONLY
│
├── src/                     Capas de datos y de negocio
│   ├── config.py            Catálogo de plazas, umbrales, paleta, patrones
│   ├── data_loader.py       Lectura de Excel y caché por firma de archivo
│   ├── data_model.py        Normalización a tablas largas
│   ├── metrics.py           Fórmulas de KPI y formato numérico
│   ├── analytics.py         Contribución a la desviación, tendencias, benchmark
│   ├── alerts.py            Motor de alertas priorizadas
│   └── insights.py          Hallazgos automáticos
│
├── components/              Capa de presentación
│   ├── layout.py            Encabezado, secciones, estilos
│   ├── filters.py           Filtros globales dependientes
│   ├── kpi_cards.py         Tarjetas, alertas y hallazgos
│   ├── charts.py            Plotly con formato ARCO centralizado
│   └── tables.py            Tablas y descargas
│
├── assets/styles.css
├── scripts/validar_fuentes.py   Conciliación contra el reporte oficial
└── deploy/                  Configuración de Nginx, IIS, systemd y Azure
```

La separación es estricta: la interfaz nunca toca la estructura del Excel y
ninguna gráfica calcula un indicador por su cuenta.

---

## Requisitos

- Python 3.10 o superior
- Los tres archivos fuente en `data/raw/`

---

## Instalación

```bash
python -m venv .venv
```

Activación del entorno:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

Ejecución:

```bash
streamlit run app.py
```

El tablero abre en `http://localhost:8501`.

---

## Archivos esperados

Se colocan en `data/raw/` y se reconocen **por patrón**, de modo que el mes
puede seguir formando parte del nombre.

| Fuente | Patrón | Hojas que se leen |
|---|---|---|
| Financiero | `RF_Comparativos*.xlsx` | `2026R`, `2026P`, `2025R`, `CBA + TORR (RENTA)`, `P2K` |
| Afluencia y aforo | `AFLUENCIA*.xlsx` | `MENSUAL`, `AFORO` |
| Cartera | `Historico_detalle_Clientes*.xlsm` | `Historico …`, `… Job` |
| Ocupación y GLA | `OCUP*.xlsx` | primera hoja |

### Actualización mensual

1. Reemplazar los archivos en `data/raw/` conservando el patrón de nombre.
2. Pulsar **Recargar fuentes** en la barra lateral (o reiniciar la aplicación).
3. Ejecutar `python scripts/validar_fuentes.py` y confirmar que la conciliación
   cierra antes de presentar las cifras.

El periodo de corte se detecta automáticamente desde los encabezados de fecha
del libro financiero, no desde el nombre del archivo ni la fecha del sistema.

---

## Configuración

La variable de entorno `ARCO_DATA_DIR` define dónde están los archivos fuente.
Si no se define, se usa `data/raw` dentro del proyecto. En servidor conviene
apuntarla a un recurso de red o a un montaje, de modo que la actualización
mensual no requiera volver a desplegar.

La variable `ARCO_ENTORNO` etiqueta la instancia en el encabezado. Es necesaria
cuando el tablero corre en más de un ambiente: sin ella, dos instancias con
datos de meses distintos son indistinguibles a simple vista.

El resto de lo parametrizable vive en `src/config.py`:

- **Catálogo de unidades** (`UNIDADES`): nombre, ciudad, columnas del libro
  financiero, códigos de cartera y códigos de afluencia y aforo.
- **Umbrales de alerta** (`UMBRALES`): días cartera objetivo y crítico,
  desviación relevante contra presupuesto, caída de margen, periodos de
  deterioro consecutivo, concentración por cliente.
- **Patrones de archivo** (`FILE_PATTERNS`) y **hojas** (`SHEET_ESCENARIOS`).
- **Paleta institucional** (`PALETA`, `SECUENCIA_COLORES`).

Dar de alta una plaza nueva es agregar una entrada a `UNIDADES`. No hay
catálogos escritos dentro de las gráficas.

Si se requieren credenciales en el futuro, se declaran en
`.streamlit/secrets.toml` o en variables de entorno; nunca en el código.

---

## Supuestos

- **UAIIDA de Ceiba + Torres.** El consolidado ejecutivo descuenta la partida
  *Renta de Terreno* (operación Sakly), tal como lo hace la hoja
  `CBA + TORR (RENTA)`. Sin este ajuste el UAIIDA de la unidad sería
  $16.27 M en lugar de los $13.30 M que reporta el Comité. El tablero anterior
  mostraba el encabezado con el criterio ajustado y el detalle por rubro con el
  criterio sin ajustar; aquí ambos usan el mismo.
- **Consolidado del portafolio.** Se calcula sumando las unidades seleccionadas
  en los filtros, no leyendo la fila `SUMA` del Excel. Así todas las secciones
  responden al mismo filtro y no puede ocurrir que una tarjeta muestre ARCO
  completo y una gráfica una sola plaza.
- **Días cartera.** `saldo ÷ facturación acumulada × 30 × meses transcurridos`,
  replicando el cálculo del libro de cobranza.
- **Cartera de Ceiba.** Se consideran Ceiba y Torres; se excluyen Pantallas y
  Kuadro para que la cartera cuadre con la definición financiera de la unidad.
- **Ocupación ponderada por GLA.** La ocupación del portafolio es
  `m² arrendados ÷ m² rentables`, no el promedio de los porcentajes de las
  plazas. Con las cifras de junio 2026 ambos métodos difieren: el ponderado da
  94.04 % y el promedio simple 91.26 %, porque trataría igual a Paseo Azahares
  (7 mil m²) y a Ceiba + Torres (79 mil m²).
- **Renta en riesgo.** Estimación: aplica la renta mínima por m² arrendado de
  cada plaza a sus m² disponibles. Supone que el espacio vacante se colocaría al
  precio promedio vigente de esa plaza, lo cual es optimista si los locales
  vacíos son los peor ubicados.
- **Indicadores por m².** Se dividen entre los m² *arrendados*, no entre el GLA
  total, para que el rendimiento no se castigue dos veces por la vacancia.
- **Unidades inactivas.** Las unidades sin movimiento en el periodo (PLA, PPB,
  HOT, DEPTOS) quedan fuera del tablero automáticamente.

---

## Limitaciones

- **Ocupación sin historia.** El archivo de ocupación entrega la foto del mes
  de corte, no la serie. No es posible mostrar la evolución de la vacancia ni
  detectar deterioro sostenido en comercialización. Si se conservan los archivos
  mensuales, el modelo admite la serie sin cambios en la interfaz.
- **Ocupación sin desglose por local.** Se reporta superficie agregada por
  plaza, no local por local, de modo que no puede analizarse la vacancia por
  tipo de espacio, nivel o giro.
- **Cartera sin clasificar.** El archivo de cobranza reporta el saldo total por
  cliente pero no distingue cartera corriente de cartera en proceso legal. Esa
  clasificación debe solicitarse a Jurídico y Cobranza.
- **Afluencia peatonal incompleta.** Plaza Centenario, Paseo Azahares y Paseo
  Esperanza no reportan afluencia; sus indicadores por visita se muestran como
  N/D en lugar de estimarse.
- **Sin histórico financiero mensual.** El libro financiero entrega el mes de
  corte y el acumulado, no la serie mensual del año. Las series históricas del
  tablero provienen de afluencia y aforo (2019–2026) y de cartera (últimos
  meses). Si Finanzas puede exportar el P&L mensual, el tablero admite la serie
  sin cambios en la interfaz.
- **Un solo periodo de presupuesto.** El comparativo contra presupuesto usa el
  escenario vigente del libro; no hay versiones de reforecast.

---

## Publicación

Guías autocontenidas por ambiente:

- **[DEPLOY_AZURE_PORTAL.md](DEPLOY_AZURE_PORTAL.md)** — Azure App Service desde el portal
- **[DEPLOY_AZURE.md](DEPLOY_AZURE.md)** — lo mismo, con Azure CLI
- **[DEPLOY_WINDOWS_IIS.md](DEPLOY_WINDOWS_IIS.md)** — Windows Server con IIS
- **[DEPLOY.md](DEPLOY.md)** — índice, Docker y reglas para operar ambos en paralelo

La aplicación necesita un intérprete de Python en ejecución, no basta con un
servidor de archivos estáticos.

| Opción | Cuándo conviene |
|---|---|
| Servidor interno de ARCO | Datos que no deben salir de la red corporativa. Ejecutar detrás de IIS o Nginx como proxy inverso. |
| Azure App Service / Container Apps | Ya existe tenant de Microsoft; integra con Entra ID para el control de acceso. |
| Streamlit Community Cloud | Pruebas y demostraciones. No recomendado con datos financieros reales. |

Ejecución en servidor:

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

El tablero no incluye autenticación propia: el control de acceso debe resolverse
en la capa de red o de proxy, que es donde ARCO ya administra identidades.
