"""
Capa 1 — Modelo normalizado.

Convierte las hojas de Excel en tablas largas (tidy) independientes de la
estructura física del archivo:

    pl                 unidad · categoria · concepto · alcance · escenario · valor
    trafico            unidad · tipo · anio · mes · valor
    cartera_hist       unidad · anio · mes · saldo
    cartera_kpi        unidad · dias_cartera · facturacion_acum
    cartera_clientes   unidad · cliente · anio · mes · saldo
    facturacion_rubro  rubro · anio · mes · valor          (portafolio)
    ocupacion          unidad · ocupacion_pct               (opcional)

Cualquier migración futura (SQL Server, Fabric, API) sólo debe reproducir estas
tablas para que la aplicación siga funcionando sin cambios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, data_loader as dl

# Layout de columnas de las hojas con formato "plaza" (una plaza por hoja).
COLMAP_PLAZA = {
    ("mes", "real_actual"): 2,
    ("mes", "ppto_actual"): 5,
    ("mes", "real_anterior"): 10,
    ("acum", "real_actual"): 15,
    ("acum", "ppto_actual"): 18,
    ("acum", "real_anterior"): 23,
}

# Desplazamiento del bloque acumulado en las hojas matriciales (2026R/2026P/2025R).
OFFSET_ACUM = 16
FILA_ENCABEZADO_PLAZAS = 4
COL_PRIMERA_PLAZA = 2


# --------------------------------------------------------------- utils ----

def _norm(x) -> str:
    return "" if pd.isna(x) else str(x).strip()


def _num(x) -> float:
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _find_row(df: pd.DataFrame, label: str, start: int = 0, exact: bool = True) -> int:
    """Índice de la primera fila cuya columna A coincide con `label`."""
    col = df.iloc[start:, 0]
    for idx, val in col.items():
        s = _norm(val)
        if (s == label) if exact else s.startswith(label):
            return idx
    raise KeyError(f"No se encontró la fila '{label}' en la hoja.")


# ------------------------------------------------- estado de resultados ----

def _plaza_columns(df: pd.DataFrame) -> dict[str, int]:
    """Mapa {clave de plaza -> columna} del bloque mensual de una hoja matricial."""
    fila = df.iloc[FILA_ENCABEZADO_PLAZAS]
    salida = {}
    for c in range(COL_PRIMERA_PLAZA, min(len(fila), COL_PRIMERA_PLAZA + OFFSET_ACUM)):
        etiqueta = _norm(fila[c])
        if etiqueta:
            salida[etiqueta] = c
    return salida


def _concept_rows(df: pd.DataFrame) -> list[tuple[str, str, int]]:
    """
    Devuelve [(categoria, concepto, fila)] recorriendo la estructura del P&L.

    Se localiza por etiquetas ancla en lugar de índices fijos: si el contador
    inserta filas, el modelo sigue leyendo el rubro correcto.
    """
    filas: list[tuple[str, str, int]] = []

    r_ini = _find_row(df, config.ANCLA_INGRESOS_NETOS)
    r_fin = _find_row(df, config.ANCLA_TOTAL_INGRESOS_NETOS, start=r_ini)
    for i in range(r_ini + 1, r_fin):
        etiqueta = _norm(df.iloc[i, 0])
        if etiqueta and etiqueta not in config.NO_RUBROS:
            filas.append(("ingreso", etiqueta, i))

    r_gastos = _find_row(df, config.ANCLA_GASTOS_OPERACION)
    r_rubros = _find_row(df, config.ANCLA_GASTOS_POR_RUBRO, start=r_gastos)
    r_cc = _find_row(df, config.ANCLA_GASTOS_POR_CC, start=r_rubros)
    for i in range(r_rubros + 1, r_cc):
        etiqueta = _norm(df.iloc[i, 0])
        if etiqueta:
            filas.append(("gasto", etiqueta, i))

    r_otras = _find_row(df, config.ANCLA_OTRAS_PARTIDAS, start=r_cc)
    for i in range(r_cc + 1, r_otras):
        etiqueta = _norm(df.iloc[i, 0])
        if etiqueta:
            filas.append(("gasto_cc", etiqueta, i))

    filas.append(("total", "Total Ingresos Netos", r_fin))
    filas.append(("total", "Gastos de Operación", r_gastos))
    filas.append(("total", "UAIIDA Ajustado", _find_row(df, config.ANCLA_UAIIDA_AJUSTADO)))
    filas.append(("total", "UAIIDA", _find_row(df, config.ANCLA_UAIIDA)))
    return filas


def _build_pl(path: Path) -> pd.DataFrame:
    registros: list[dict] = []

    for escenario, hoja in config.SHEET_ESCENARIOS.items():
        df = dl.read_sheet(path, hoja)
        cols = _plaza_columns(df)
        conceptos = _concept_rows(df)
        for categoria, concepto, fila in conceptos:
            for plaza, c in cols.items():
                for alcance, offset in (("mes", 0), ("acum", OFFSET_ACUM)):
                    registros.append({
                        "col_origen": plaza,
                        "categoria": categoria,
                        "concepto": concepto,
                        "alcance": alcance,
                        "escenario": escenario,
                        "valor": _num(df.iloc[fila, c + offset]),
                    })

    pl = pd.DataFrame(registros)

    # Consolidación a unidades de negocio (CBA + TORR se suman).
    mapa = {}
    for clave, meta in config.UNIDADES.items():
        for col in meta["cols_financiero"]:
            mapa[col] = clave
    pl["unidad"] = pl["col_origen"].map(mapa)
    pl = pl.dropna(subset=["unidad"])
    pl = (pl.groupby(["unidad", "categoria", "concepto", "alcance", "escenario"], as_index=False)["valor"]
            .sum())

    pl = _ajuste_cba(pl, path)
    pl["ciudad"] = pl["unidad"].map(lambda u: config.UNIDADES[u]["ciudad"])
    pl["plaza"] = pl["unidad"].map(lambda u: config.UNIDADES[u]["nombre"])
    return pl


def _ajuste_cba(pl: pd.DataFrame, path: Path) -> pd.DataFrame:
    """
    Aplica el criterio ejecutivo de CBA: el UAIIDA Ajustado que se presenta al
    Comité descuenta la Renta de Terreno (operación Sakly), tal como lo hace la
    hoja 'CBA + TORR (RENTA)'. Sin este ajuste el consolidado no cuadra con el
    reporte oficial.
    """
    if "CBA+TORR" not in config.UNIDADES:
        return pl
    try:
        df = dl.read_sheet(path, config.SHEET_CBA_RENTA)
        # La partida vive en el bloque de Comisiones, después del UAIIDA Ajustado.
        # Buscar antes provocaría coincidencia con "Renta de Terrenos" (ingresos).
        inicio = _find_row(df, config.ANCLA_UAIIDA_AJUSTADO)
        fila = _find_row(df, config.ANCLA_RENTA_TERRENO, start=inicio, exact=False)
    except (KeyError, ValueError, OSError):
        return pl

    for (alcance, escenario), col in COLMAP_PLAZA.items():
        ajuste = _num(df.iloc[fila, col])
        if ajuste == 0:
            continue
        mask = (
            (pl["unidad"] == "CBA+TORR")
            & (pl["concepto"] == "UAIIDA Ajustado")
            & (pl["alcance"] == alcance)
            & (pl["escenario"] == escenario)
        )
        pl.loc[mask, "valor"] = pl.loc[mask, "valor"] - ajuste
    return pl


def _detect_period(path: Path) -> tuple[int, int]:
    """Periodo de corte a partir de los encabezados de fecha del libro financiero."""
    for hoja in ("P2K", "TOTAL"):
        try:
            df = dl.read_sheet(path, hoja)
        except Exception:
            continue
        valor = df.iloc[4, 2]
        if isinstance(valor, pd.Timestamp):
            return int(valor.year), int(valor.month)
        try:
            ts = pd.to_datetime(valor)
            return int(ts.year), int(ts.month)
        except Exception:
            continue
    return pd.Timestamp.today().year, pd.Timestamp.today().month


# ---------------------------------------------------- afluencia y aforo ----

def _parse_traffic_sheet(df: pd.DataFrame, fila_plaza: int, fila_anio: int,
                         fila_primer_mes: int) -> pd.DataFrame:
    """
    Las hojas de afluencia/aforo son bloques horizontales de ancho variable, uno
    por plaza, con una columna por año y columnas auxiliares de variación. Se
    detecta el inicio de cada bloque por la etiqueta de plaza y las columnas de
    datos por su encabezado de año.
    """
    encabezados = df.iloc[fila_plaza]
    inicios = [c for c in range(df.shape[1]) if _norm(encabezados[c])]
    registros = []

    for i, c0 in enumerate(inicios):
        plaza = _norm(encabezados[c0])
        c1 = inicios[i + 1] if i + 1 < len(inicios) else df.shape[1]
        vistos: set[int] = set()
        for c in range(c0, c1):
            bruto = df.iloc[fila_anio, c]
            try:
                anio = int(float(bruto))
            except (TypeError, ValueError):
                continue
            if not (2000 <= anio <= 2100) or anio in vistos:
                continue
            columna = df.iloc[fila_primer_mes:fila_primer_mes + 12, c]
            valores = [_num(v) for v in columna]
            # Las columnas de variación traen porcentajes: se descartan.
            if max(valores) < 100:
                continue
            vistos.add(anio)
            for m, v in enumerate(valores, start=1):
                if v > 0:
                    registros.append({"cod": plaza, "anio": anio, "mes": m, "valor": v})
    return pd.DataFrame(registros)


def _build_traffic(path: Path) -> pd.DataFrame:
    piezas = []
    afl = _parse_traffic_sheet(dl.read_sheet(path, config.SHEET_AFLUENCIA), 2, 3, 5)
    afl["tipo"] = "afluencia"
    afo = _parse_traffic_sheet(dl.read_sheet(path, config.SHEET_AFORO), 2, 3, 5)
    afo["tipo"] = "aforo"

    for df, campo in ((afl, "cod_afluencia"), (afo, "cod_aforo")):
        mapa = {config.UNIDADES[u][campo]: u for u in config.UNIDADES
                if config.UNIDADES[u][campo]}
        df = df.copy()
        df["unidad"] = df["cod"].map(mapa)
        piezas.append(df.dropna(subset=["unidad"]))

    trafico = pd.concat(piezas, ignore_index=True)
    trafico["ciudad"] = trafico["unidad"].map(lambda u: config.UNIDADES[u]["ciudad"])
    trafico["plaza"] = trafico["unidad"].map(lambda u: config.UNIDADES[u]["nombre"])
    return trafico[["unidad", "plaza", "ciudad", "tipo", "anio", "mes", "valor"]]


# -------------------------------------------------------------- cartera ----

def _mes_from_label(label: str) -> int | None:
    """'06. Junio' -> 6 ; '02. Febrero ' -> 2"""
    s = _norm(label)
    if not s:
        return None
    cabeza = s.split(".")[0].strip()
    if cabeza.isdigit():
        n = int(cabeza)
        return n if 1 <= n <= 12 else None
    for i, nombre in enumerate(config.MESES_ES, start=1):
        if nombre.lower() in s.lower():
            return i
    return None


def _resolve_sheet(path: Path, preferida: str, contiene: str) -> str:
    """El nombre de hoja incluye el mes ('Historico Jun 26'); se resuelve por contenido."""
    hojas = dl.sheet_names(path)
    if preferida in hojas:
        return preferida
    for h in hojas:
        if contiene.lower() in h.lower():
            return h
    raise KeyError(f"No se encontró una hoja que contenga '{contiene}' en {path.name}")


def _build_cartera(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    hoja_hist = _resolve_sheet(path, config.SHEET_CARTERA_HIST, "historico")
    df = dl.read_sheet(path, hoja_hist)

    fila_anio, fila_mes = 4, 5
    # Columnas de la serie mensual: encabezado tipo '01. Enero' con año arriba.
    columnas: list[tuple[int, int, int]] = []  # (col, anio, mes)
    anio_actual = None
    for c in range(df.shape[1]):
        bruto = df.iloc[fila_anio, c]
        try:
            anio_actual = int(float(bruto))
        except (TypeError, ValueError):
            pass
        mes = _mes_from_label(df.iloc[fila_mes, c])
        if mes and anio_actual and 2000 <= anio_actual <= 2100:
            columnas.append((c, anio_actual, mes))

    # Filas de plaza: '002. P2K', '216. TORR', ... hasta 'TOTAL'.
    registros, kpis = [], []
    col_dc = df.shape[1] - 1
    col_fact = None
    for c in range(df.shape[1]):
        if "fact acum" in _norm(df.iloc[fila_mes, c]).lower():
            col_fact = c
        if _norm(df.iloc[fila_mes, c]).upper() == "DC":
            col_dc = c

    mapa_cod = {}
    for clave, meta in config.UNIDADES.items():
        for cod in meta["cod_cartera"]:
            mapa_cod[cod] = clave

    for i in range(fila_mes + 1, df.shape[0]):
        etiqueta = _norm(df.iloc[i, 1])
        if etiqueta.upper() == "TOTAL":
            break
        unidad = mapa_cod.get(etiqueta)
        if unidad is None:
            continue
        for c, anio, mes in columnas:
            registros.append({"unidad": unidad, "anio": anio, "mes": mes,
                              "saldo": _num(df.iloc[i, c])})
        kpis.append({
            "unidad": unidad,
            "facturacion_acum": _num(df.iloc[i, col_fact]) if col_fact else 0.0,
            "dias_cartera_raw": _num(df.iloc[i, col_dc]),
        })

    hist = (pd.DataFrame(registros)
            .groupby(["unidad", "anio", "mes"], as_index=False)["saldo"].sum())
    kpi = (pd.DataFrame(kpis)
           .groupby("unidad", as_index=False)["facturacion_acum"].sum())

    # Detalle por cliente.
    hoja_det = _resolve_sheet(path, config.SHEET_CARTERA_DETALLE, "job")
    dd = dl.read_sheet(path, hoja_det)
    fila_anio_d, fila_mes_d = 1, 2
    cols_d: list[tuple[int, int, int]] = []
    anio_actual = None
    for c in range(dd.shape[1]):
        try:
            anio_actual = int(float(dd.iloc[fila_anio_d, c]))
        except (TypeError, ValueError):
            pass
        mes = _mes_from_label(dd.iloc[fila_mes_d, c])
        if mes and anio_actual and 2000 <= anio_actual <= 2100:
            cols_d.append((c, anio_actual, mes))

    det = []
    for i in range(fila_mes_d + 1, dd.shape[0]):
        cliente = _norm(dd.iloc[i, 0])
        plaza_txt = _norm(dd.iloc[i, 1]).upper()
        if not cliente or cliente.upper() == "TOTAL":
            continue
        unidad = config.MAPA_PLAZA_CARTERA_DETALLE.get(plaza_txt)
        if unidad not in config.UNIDADES:
            continue
        for c, anio, mes in cols_d:
            v = _num(dd.iloc[i, c])
            if v != 0:
                det.append({"unidad": unidad, "cliente": cliente,
                            "anio": anio, "mes": mes, "saldo": v})
    detalle = (pd.DataFrame(det)
               .groupby(["unidad", "cliente", "anio", "mes"], as_index=False)["saldo"].sum())

    # Facturación mensual por rubro (portafolio) — base del cálculo de días cartera.
    fact = _build_facturacion_rubro(df)
    return hist, kpi, detalle, fact


def _build_facturacion_rubro(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla dinámica de facturación mensual por rubro incluida en el libro de cartera."""
    try:
        fila_titulo = _find_row(df.rename(columns={1: 0}), "Etiquetas de fila", exact=False)
    except KeyError:
        fila_titulo = None
    if fila_titulo is None:
        # búsqueda directa en la columna B
        fila_titulo = None
        for i in range(df.shape[0]):
            if _norm(df.iloc[i, 1]).lower().startswith("etiquetas de fila"):
                fila_titulo = i
                break
    if fila_titulo is None:
        return pd.DataFrame(columns=["rubro", "anio", "mes", "valor"])

    anio = None
    for i in range(max(0, fila_titulo - 3), fila_titulo):
        for c in range(df.shape[1]):
            try:
                cand = int(float(df.iloc[i, c]))
                if 2000 <= cand <= 2100:
                    anio = cand
            except (TypeError, ValueError):
                continue
    cols = []
    for c in range(df.shape[1]):
        mes = _mes_from_label(df.iloc[fila_titulo, c])
        if mes:
            cols.append((c, mes))

    filas = []
    for i in range(fila_titulo + 1, df.shape[0]):
        rubro = _norm(df.iloc[i, 1])
        if not rubro:
            continue
        if rubro.lower().startswith("total"):
            break
        for c, mes in cols:
            filas.append({"rubro": rubro, "anio": anio or 0, "mes": mes,
                          "valor": _num(df.iloc[i, c])})
    return pd.DataFrame(filas)


# ------------------------------------------------------------ ocupación ----

def _build_ocupacion() -> pd.DataFrame:
    """
    Ocupación de área rentable (GLA).

    El archivo entrega, por plaza, la superficie arrendada, la superficie
    disponible, el GLA total y el porcentaje de ocupación. Se leen las cuatro
    magnitudes —no sólo el porcentaje— porque el GLA es el denominador que
    permite comparar plazas de tamaños distintos (ingreso por m², gasto por m²)
    y valorar la superficie vacante.

    El layout se localiza por encabezados y no por posición fija: las columnas
    de superficie arrendada y disponible vienen sin título en el archivo, así
    que se identifican verificando cuál reconstruye el porcentaje reportado.
    """
    columnas = ["unidad", "gla_total", "gla_ocupada", "gla_vacante", "ocupacion_pct"]
    vacio = pd.DataFrame(columns=columnas)

    path = dl.resolve_source("ocupacion")
    if path is None:
        return vacio
    try:
        df = pd.read_excel(path, sheet_name=0, header=None, engine="openpyxl")
    except Exception:
        return vacio

    # Fila de encabezados: la que contiene la etiqueta PLAZA.
    fila_hdr = col_plaza = None
    for i in range(df.shape[0]):
        for c in range(df.shape[1]):
            if _norm(df.iloc[i, c]).upper() == config.OCUP_ENCABEZADO_PLAZA:
                fila_hdr, col_plaza = i, c
                break
        if fila_hdr is not None:
            break
    if fila_hdr is None:
        return vacio

    encabezados = {_norm(df.iloc[fila_hdr, c]).upper(): c for c in range(df.shape[1])
                   if _norm(df.iloc[fila_hdr, c])}
    col_gla = encabezados.get(config.OCUP_ENCABEZADO_GLA)
    col_pct = encabezados.get(config.OCUP_ENCABEZADO_PCT)
    if col_gla is None or col_pct is None:
        return vacio

    nombres = {v["nombre"].upper(): k for k, v in config.UNIDADES.items()}
    filas = []
    for i in range(fila_hdr + 1, df.shape[0]):
        etiqueta = _norm(df.iloc[i, col_plaza])
        if not etiqueta or etiqueta.upper() in ("TOTAL", "SUMA"):
            continue
        unidad = etiqueta if etiqueta in config.UNIDADES else nombres.get(etiqueta.upper())
        if unidad is None:
            continue
        gla = _num(df.iloc[i, col_gla])
        pct = _num(df.iloc[i, col_pct])
        if gla <= 0:
            continue
        if pct > 1.5:  # el archivo puede venir en escala 0-100
            pct = pct / 100
        filas.append({"fila": i, "unidad": unidad, "gla_total": gla, "ocupacion_pct": pct})

    if not filas:
        return vacio
    base = pd.DataFrame(filas)

    # Identificación de las columnas sin título: la que reproduce gla × % es la
    # superficie arrendada; la que reproduce gla × (1 − %) es la disponible.
    col_ocupada = col_vacante = None
    esperado_ocupada = base["gla_total"] * base["ocupacion_pct"]
    esperado_vacante = base["gla_total"] * (1 - base["ocupacion_pct"])
    for c in range(df.shape[1]):
        if c in (col_gla, col_pct, col_plaza):
            continue
        valores = pd.Series([_num(df.iloc[i, c]) for i in base["fila"]])
        if valores.sum() <= 0:
            continue
        tolerancia = max(1.0, base["gla_total"].sum() * 0.001)
        if col_ocupada is None and abs(valores.sum() - esperado_ocupada.sum()) < tolerancia:
            col_ocupada = c
        elif col_vacante is None and abs(valores.sum() - esperado_vacante.sum()) < tolerancia:
            col_vacante = c

    if col_ocupada is not None:
        base["gla_ocupada"] = [_num(df.iloc[i, col_ocupada]) for i in base["fila"]]
    else:
        base["gla_ocupada"] = esperado_ocupada
    if col_vacante is not None:
        base["gla_vacante"] = [_num(df.iloc[i, col_vacante]) for i in base["fila"]]
    else:
        base["gla_vacante"] = base["gla_total"] - base["gla_ocupada"]

    return base[columnas].reset_index(drop=True)


# --------------------------------------------------------------- modelo ----

@dataclass
class ModeloARCO:
    pl: pd.DataFrame
    trafico: pd.DataFrame
    cartera_hist: pd.DataFrame
    cartera_kpi: pd.DataFrame
    cartera_clientes: pd.DataFrame
    facturacion_rubro: pd.DataFrame
    ocupacion: pd.DataFrame
    anio: int
    mes: int
    fuentes: dict = field(default_factory=dict)
    supuestos: list[str] = field(default_factory=list)

    @property
    def periodo_label(self) -> str:
        return f"{config.MESES_ES[self.mes - 1]} {self.anio}"

    @property
    def acumulado_label(self) -> str:
        return f"Enero–{config.MESES_ES[self.mes - 1]} {self.anio}"

    @property
    def unidades_activas(self) -> list[str]:
        con_datos = set(
            self.pl.loc[(self.pl["concepto"] == "Total Ingresos Netos")
                        & (self.pl["valor"] != 0), "unidad"]
        )
        return [u for u in config.ORDEN_UNIDADES if u in con_datos]


def build_model(data_dir: Path | None = None) -> ModeloARCO:
    """Construye el modelo normalizado completo a partir de data/raw."""
    p_fin = dl.require_source("financiero", data_dir)
    p_afl = dl.require_source("afluencia", data_dir)
    p_car = dl.require_source("cartera", data_dir)

    pl = _build_pl(p_fin)
    anio, mes = _detect_period(p_fin)
    trafico = _build_traffic(p_afl)
    hist, kpi, detalle, fact = _build_cartera(p_car)
    ocupacion = _build_ocupacion()

    supuestos = [
        "El UAIIDA Ajustado de Ceiba + Torres descuenta la Renta de Terreno "
        "(operación Sakly), replicando el criterio de la hoja 'CBA + TORR (RENTA)'.",
        "El portafolio se calcula sumando las unidades seleccionadas en los filtros; "
        "no se lee de la fila SUMA del Excel, para que todas las secciones respondan "
        "al mismo filtro.",
        "Afluencia peatonal no se reporta para Plaza Centenario, Paseo Azahares ni "
        "Paseo Esperanza; sus indicadores por visita se muestran como N/D.",
    ]
    if ocupacion.empty:
        supuestos.append(
            "No se detectó archivo de ocupación en data/raw. Es un concepto distinto "
            "de afluencia y aforo (mide superficie arrendada, no visitas) y no puede "
            "derivarse de ellos: coloque el archivo OCUP para activarlo."
        )
    else:
        supuestos.append(
            "La ocupación del portafolio se pondera por GLA, no se promedia entre "
            "plazas: una plaza de 7 mil m² no pesa lo mismo que una de 79 mil m²."
        )
        supuestos.append(
            "La renta en riesgo por superficie vacante es una estimación: aplica la "
            "renta mínima por m² arrendado de cada plaza a sus m² disponibles. "
            "Supone que el espacio vacante se colocaría al precio promedio vigente."
        )
        faltantes = [config.UNIDADES[u]["nombre"] for u in config.ORDEN_UNIDADES
                     if u not in set(ocupacion["unidad"])]
        if faltantes:
            supuestos.append("Sin ocupación reportada para: " + ", ".join(faltantes) + ".")

    return ModeloARCO(
        pl=pl, trafico=trafico, cartera_hist=hist, cartera_kpi=kpi,
        cartera_clientes=detalle, facturacion_rubro=fact, ocupacion=ocupacion,
        anio=anio, mes=mes,
        fuentes={"financiero": p_fin, "afluencia": p_afl, "cartera": p_car},
        supuestos=supuestos,
    )
