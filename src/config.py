"""
Configuración central de negocio para el tablero ejecutivo de ARCO.

Toda la parametrización que puede cambiar por decisión de negocio (catálogo de
plazas, agrupaciones, umbrales de alerta, patrones de archivo) vive aquí y no
dentro de la capa de presentación.
"""

from pathlib import Path
import os

# ---------------------------------------------------------------- rutas ----

BASE_DIR = Path(__file__).resolve().parent.parent

# En despliegue, los archivos fuente suelen vivir fuera del código: un recurso
# compartido de red, un montaje de Azure Files o un volumen de Docker. La
# variable ARCO_DATA_DIR permite apuntar ahí sin tocar el proyecto.
DATA_RAW = Path(os.getenv("ARCO_DATA_DIR", BASE_DIR / "data" / "raw"))
ASSETS = BASE_DIR / "assets"

# ------------------------------------------------------------- entorno ----

# Cuando el tablero corre en más de un ambiente (por ejemplo Azure y servidor
# interno durante una evaluación), esta etiqueta se muestra en el encabezado.
# Sin ella, dos instancias con datos de meses distintos son indistinguibles a
# simple vista y alguien terminaría citando cifras del ambiente equivocado.
ENTORNO = os.getenv("ARCO_ENTORNO", "").strip()

# Valores que se consideran el ambiente oficial: no se marca con distintivo.
ENTORNO_OFICIAL = {"produccion", "producción", "prod", "oficial"}


def entorno_es_oficial() -> bool:
    return (not ENTORNO) or ENTORNO.lower() in ENTORNO_OFICIAL

# Los archivos fuente conservan el mes en el nombre, por lo que se resuelven por
# patrón y no por nombre literal. Si ARCO estandariza el nombre, el patrón sigue
# funcionando sin cambios.
FILE_PATTERNS = {
    "financiero": ["RF_Comparativos*.xlsx", "RF_Comparativos*.xlsm"],
    "afluencia": ["AFLUENCIA*.xlsx", "AFLUENCIA*.xlsm"],
    "cartera": ["Historico_detalle_Clientes*.xlsm", "Historico_detalle_Clientes*.xlsx"],
    # El archivo de ocupación llega como OCUP_JUN26.xlsx; el patrón cubre esa
    # nomenclatura y también "ocupacion*" por si Comercialización la estandariza.
    "ocupacion": ["OCUP*.xlsx", "ocup*.xlsx", "Ocup*.xlsx"],
}

# ------------------------------------------------------- hojas estables ----

# Hojas matriciales (concepto x plaza) del libro financiero. Sus nombres NO
# incluyen el mes, a diferencia de "RESUMEN JUN26", por lo que son la fuente
# preferente para la carga automática.
SHEET_ESCENARIOS = {
    "real_actual": "2026R",
    "ppto_actual": "2026P",
    "real_anterior": "2025R",
}

ESCENARIO_LABEL = {
    "real_actual": "Real",
    "ppto_actual": "Presupuesto",
    "real_anterior": "Año anterior",
}

# Hoja con el ajuste ejecutivo de CBA (resta Renta de Terreno / Sakly).
SHEET_CBA_RENTA = "CBA + TORR  (RENTA)"

SHEET_AFLUENCIA = "MENSUAL"
SHEET_AFORO = "AFORO"
SHEET_CARTERA_HIST = "Historico Jun 26"
SHEET_CARTERA_DETALLE = "Jun 26 Job"

# Encabezados que identifican las columnas del archivo de ocupación.
OCUP_ENCABEZADO_PLAZA = "PLAZA"
OCUP_ENCABEZADO_GLA = "GLA"
OCUP_ENCABEZADO_PCT = "%"

# ------------------------------------------------------------ catálogo ----

# Unidades de negocio tal como las reporta la Dirección. CBA se consolida con
# TORR porque así se presenta al Comité (hoja "CBA + TORR (RENTA)").
UNIDADES = {
    "P2K": {
        "nombre": "Plaza Paseo 2000",
        "ciudad": "Tijuana",
        "cols_financiero": ["P2K"],
        "cod_cartera": ["002. P2K"],
        "cod_afluencia": "P2K",
        "cod_aforo": "P2K",
    },
    "PSP": {
        "nombre": "Plaza San Pedro",
        "ciudad": "Mexicali",
        "cols_financiero": ["PSP"],
        "cod_cartera": ["003. PSP"],
        "cod_afluencia": "PSP",
        "cod_aforo": "PSP",
    },
    "PRG": {
        "nombre": "Pabellón Rosarito Grand",
        "ciudad": "Playas de Rosarito",
        "cols_financiero": ["PRG"],
        "cod_cartera": ["004. PRG"],
        "cod_afluencia": "PRG",
        "cod_aforo": "PRG",
    },
    "PC": {
        "nombre": "Plaza Centenario",
        "ciudad": "Los Mochis",
        "cols_financiero": ["PC"],
        "cod_cartera": ["005. PC"],
        "cod_afluencia": None,
        "cod_aforo": "PC",
    },
    "PSI": {
        "nombre": "Paseo San Isidro",
        "ciudad": "Culiacán",
        "cols_financiero": ["PSI"],
        "cod_cartera": ["007. PSI"],
        "cod_afluencia": "PSI",
        "cod_aforo": "PSI",
    },
    "PPA": {
        "nombre": "Paseo Azahares",
        "ciudad": "Culiacán",
        "cols_financiero": ["PPA"],
        "cod_cartera": ["008. PPA"],
        "cod_afluencia": None,
        "cod_aforo": "PPA",
    },
    "CBA+TORR": {
        "nombre": "Ceiba + Torres (Renta)",
        "ciudad": "Culiacán",
        "cols_financiero": ["CBA", "TORR"],
        # Pantallas y Kuadro se excluyen para que la cartera cuadre con la
        # definición financiera de la hoja 'CBA + TORR (RENTA)'.
        "cod_cartera": ["010. CBA", "216. TORR"],
        "cod_afluencia": "CBA",
        "cod_aforo": "CBA",
    },
    "PV": {
        "nombre": "Paseo Villalta",
        "ciudad": "Saltillo",
        "cols_financiero": ["PV"],
        "cod_cartera": ["011. PV"],
        "cod_afluencia": "PV",
        "cod_aforo": "PV",
    },
    "PLP": {
        "nombre": "Paseo La Paz",
        "ciudad": "La Paz",
        "cols_financiero": ["PLP"],
        "cod_cartera": ["012. PLP"],
        "cod_afluencia": "PLP",
        "cod_aforo": "PLP",
    },
    "PE": {
        "nombre": "Paseo Esperanza",
        "ciudad": "San José del Cabo",
        "cols_financiero": ["PE"],
        "cod_cartera": ["013. PE"],
        "cod_afluencia": None,
        "cod_aforo": "PPE",
    },
}

ORDEN_UNIDADES = list(UNIDADES.keys())

# Nombres largos usados en el detalle de clientes -> clave de unidad.
MAPA_PLAZA_CARTERA_DETALLE = {
    "PLAZA PASEO 2000": "P2K",
    "PLAZA SAN PEDRO": "PSP",
    "PLAZA PABELLON": "PRG",
    "PLAZA CENTENARIO": "PC",
    "PASEO SAN ISIDRO": "PSI",
    "PASEO AZAHARES": "PPA",
    "CEIBA": "CBA+TORR",
    "TORRES CBA": "CBA+TORR",
    "PANTALLAS CBA": "PANTALLAS",
    "KUADRO CBA": "KUADRO",
    "PASEO VILLALTA": "PV",
    "PASEO LA PAZ": "PLP",
    "PASEO ESPERANZA": "PE",
    # Unidades fuera del portafolio ejecutivo (se conservan etiquetadas).
    "HOTEL CEIBA": "HOT",
    "DEPARTAMENTOS PV": "DEPTOS",
    "PASEO BICENTENARIO": "PPB",
}

CIUDADES = sorted({u["ciudad"] for u in UNIDADES.values()})

# --------------------------------------------------------- conceptos P&L ----

# Etiquetas exactas en la columna A del libro financiero.
ANCLA_INGRESOS_NETOS = "INGRESOS NETOS"
ANCLA_TOTAL_INGRESOS_NETOS = "Total Ingresos Netos"
ANCLA_GASTOS_OPERACION = "Gastos de Operación"
ANCLA_GASTOS_POR_RUBRO = "Por Rubros:"
ANCLA_GASTOS_POR_CC = "Por Centro de Costo:"
ANCLA_OTRAS_PARTIDAS = "Otras Partidas:"
ANCLA_UAIIDA_AJUSTADO = "U. A. I. I. D. A. Ajustado"
ANCLA_UAIIDA = "U. A. I. I. D. A."
ANCLA_RENTA_TERRENO = "Renta de Terreno"

# Encabezados de sección que no son rubros.
NO_RUBROS = {
    "Ingresos por Operación de Plazas:",
    "Ingresos por Servicios:",
}

KPI_TOTALES = {
    "ingresos_netos": "Ingresos Netos",
    "gastos_operacion": "Gastos de Operación",
    "uaiida_ajustado": "UAIIDA Ajustado",
    "margen_uaiida": "Margen UAIIDA",
}

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MESES_ABR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# ------------------------------------------------------------- umbrales ----

UMBRALES = {
    # Desviación relativa vs presupuesto o vs año anterior que dispara alerta.
    "desviacion_critica": 0.10,
    "desviacion_alta": 0.05,
    # Días cartera considerados sanos / de atención.
    "dc_objetivo": 25.0,
    "dc_critico": 40.0,
    # Caída de margen UAIIDA en puntos porcentuales vs año anterior.
    "margen_caida_pp": 3.0,
    # Periodos consecutivos de deterioro que disparan alerta de tendencia.
    "periodos_deterioro": 3,
    # Concentración: participación de un cliente en la cartera de su plaza.
    "concentracion_cliente": 0.30,
    # Ocupación de área rentable (GLA) considerada sana / de atención.
    "ocupacion_objetivo": 0.92,
    "ocupacion_critica": 0.85,
}

SEVERIDADES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

SEVERIDAD_LABEL = {
    "CRITICAL": "Crítica",
    "HIGH": "Alta",
    "MEDIUM": "Media",
    "LOW": "Baja",
}

# --------------------------------------------------------------- estilo ----

PALETA = {
    "azul_1": "#4a7c9e",
    "azul_2": "#384c5f",
    "mensual": "#7ccad3",
    "acumulado": "#384c5f",
    "verde": "#4f9887",
    "ambar": "#c88d52",
    "rojo": "#aa1922",
    "gris": "#8a97a1",
    "linea": "#e2e7ec",
    "tinta": "#20303d",
    "papel": "#f4f6f8",
}

SECUENCIA_COLORES = [
    "#384c5f", "#4a7c9e", "#7ccad3", "#4f9887", "#c88d52",
    "#8b7249", "#aa1922", "#722724", "#615958", "#c64b17",
]
