"""
Capa 2 — Indicadores.

Toda fórmula de KPI vive aquí. Ninguna gráfica, tabla o tarjeta recalcula un
indicador por su cuenta: piden el resultado a este módulo. Cambiar la definición
de UAIIDA o de días cartera se hace en un solo lugar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .data_model import ModeloARCO

DIAS_MES = 30

ESCENARIOS_SALIDA = {
    "real_actual": "real",
    "ppto_actual": "ppto",
    "real_anterior": "ly",
}


# ------------------------------------------------------------- formato ----

def format_currency(valor, decimales: int = 0) -> str:
    """$1,234,567 — importe completo, para tablas de detalle."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "N/D"
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor):,.{decimales}f}"


def format_millions(valor, sufijo: str = " M") -> str:
    """$8.45 M — magnitud ejecutiva, evita precisión falsa."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "N/D"
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor) / 1e6:,.2f}{sufijo}"


def format_number(valor, decimales: int = 0) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "N/D"
    return f"{valor:,.{decimales}f}"


def format_percentage(valor, decimales: int = 1, ya_en_pct: bool = False) -> str:
    """0.947 -> 94.7 % (o 94.7 -> 94.7 % si ya viene en escala porcentual)."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "N/D"
    v = valor if ya_en_pct else valor * 100
    return f"{v:,.{decimales}f} %"


def format_variation(valor, decimales: int = 1, ya_en_pct: bool = False) -> str:
    """+12.4 % / -3.1 % — siempre con signo explícito."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "N/D"
    v = valor if ya_en_pct else valor * 100
    return f"{'+' if v >= 0 else ''}{v:,.{decimales}f} %"


def format_auto(valor, tipo: str) -> str:
    if tipo == "moneda":
        return format_millions(valor)
    if tipo == "porcentaje":
        return format_percentage(valor)
    return format_number(valor)


# ----------------------------------------------------------- variaciones ----

def calculate_variance(actual, referencia) -> dict:
    """Variación absoluta y relativa contra una referencia (presupuesto o año anterior)."""
    if referencia in (None, 0) or pd.isna(referencia):
        return {"abs": (actual or 0) - (referencia or 0), "pct": None}
    return {"abs": actual - referencia, "pct": actual / referencia - 1}


def calculate_yoy(actual, anterior):
    """Variación año contra año."""
    return calculate_variance(actual, anterior)["pct"]


def calculate_vs_budget(real, presupuesto):
    """Cumplimiento y desviación contra presupuesto."""
    v = calculate_variance(real, presupuesto)
    return {"desviacion_abs": v["abs"], "desviacion_pct": v["pct"],
            "cumplimiento": (real / presupuesto) if presupuesto else None}


# -------------------------------------------------- consultas al modelo ----

def filtrar_unidades(modelo: ModeloARCO, unidades: list[str] | None) -> list[str]:
    activas = modelo.unidades_activas
    if not unidades:
        return activas
    return [u for u in activas if u in unidades]


def pl_por_unidad(modelo: ModeloARCO, concepto: str, alcance: str = "mes",
                  unidades: list[str] | None = None) -> pd.DataFrame:
    """Tabla unidad × escenario (real / ppto / ly) para un concepto del P&L."""
    unidades = filtrar_unidades(modelo, unidades)
    df = modelo.pl[(modelo.pl["concepto"] == concepto)
                   & (modelo.pl["alcance"] == alcance)
                   & (modelo.pl["unidad"].isin(unidades))]
    out = df.pivot_table(index="unidad", columns="escenario", values="valor",
                         aggfunc="sum").rename(columns=ESCENARIOS_SALIDA)
    for c in ("real", "ppto", "ly"):
        if c not in out.columns:
            out[c] = 0.0
    out = out.reindex([u for u in config.ORDEN_UNIDADES if u in out.index])
    out["plaza"] = [config.UNIDADES[u]["nombre"] for u in out.index]
    out["ciudad"] = [config.UNIDADES[u]["ciudad"] for u in out.index]
    return out[["plaza", "ciudad", "real", "ppto", "ly"]]


def pl_rubros(modelo: ModeloARCO, categoria: str, alcance: str = "mes",
              unidades: list[str] | None = None) -> pd.DataFrame:
    """Detalle por rubro (ingreso o gasto) agregado sobre las unidades filtradas."""
    unidades = filtrar_unidades(modelo, unidades)
    df = modelo.pl[(modelo.pl["categoria"] == categoria)
                   & (modelo.pl["alcance"] == alcance)
                   & (modelo.pl["unidad"].isin(unidades))]
    out = (df.pivot_table(index="concepto", columns="escenario", values="valor",
                          aggfunc="sum")
             .rename(columns=ESCENARIOS_SALIDA))
    for c in ("real", "ppto", "ly"):
        if c not in out.columns:
            out[c] = 0.0
    out = out[(out[["real", "ppto", "ly"]].abs().sum(axis=1) > 0)]
    return out[["real", "ppto", "ly"]].sort_values("real", ascending=False)


def kpis_portafolio(modelo: ModeloARCO, alcance: str = "mes",
                    unidades: list[str] | None = None) -> dict:
    """
    Bloque de indicadores consolidados: ingresos, gastos, UAIIDA ajustado y
    margen, cada uno con su comparativo contra presupuesto y contra año anterior.
    """
    salida = {}
    for clave, concepto in (("ingresos", "Total Ingresos Netos"),
                            ("gastos", "Gastos de Operación"),
                            ("uaiida", "UAIIDA Ajustado")):
        t = pl_por_unidad(modelo, concepto, alcance, unidades)[["real", "ppto", "ly"]].sum()
        salida[clave] = {
            "real": t["real"], "ppto": t["ppto"], "ly": t["ly"],
            "var_ly": calculate_yoy(t["real"], t["ly"]),
            "var_ppto": calculate_vs_budget(t["real"], t["ppto"])["desviacion_pct"],
            "desv_ppto_abs": t["real"] - t["ppto"],
        }
    ing, ua = salida["ingresos"], salida["uaiida"]
    salida["margen"] = {
        "real": ua["real"] / ing["real"] if ing["real"] else None,
        "ppto": ua["ppto"] / ing["ppto"] if ing["ppto"] else None,
        "ly": ua["ly"] / ing["ly"] if ing["ly"] else None,
    }
    m = salida["margen"]
    salida["margen"]["delta_ly_pp"] = (
        (m["real"] - m["ly"]) * 100 if m["real"] is not None and m["ly"] is not None else None
    )
    return salida


# ---------------------------------------------------- afluencia y aforo ----

def trafico_periodo(modelo: ModeloARCO, tipo: str, anio: int, mes: int,
                    unidades: list[str] | None = None, acumulado: bool = False) -> pd.Series:
    """Afluencia o aforo del mes (o acumulado enero–mes) por unidad."""
    unidades = filtrar_unidades(modelo, unidades)
    t = modelo.trafico
    mask = (t["tipo"] == tipo) & (t["anio"] == anio) & (t["unidad"].isin(unidades))
    mask &= (t["mes"] <= mes) if acumulado else (t["mes"] == mes)
    return t[mask].groupby("unidad")["valor"].sum()


def trafico_comparativo(modelo: ModeloARCO, tipo: str, unidades: list[str] | None = None,
                        acumulado: bool = False) -> pd.DataFrame:
    """Comparativo del periodo actual contra el mismo periodo del año anterior."""
    act = trafico_periodo(modelo, tipo, modelo.anio, modelo.mes, unidades, acumulado)
    ant = trafico_periodo(modelo, tipo, modelo.anio - 1, modelo.mes, unidades, acumulado)
    out = pd.DataFrame({"actual": act, "anterior": ant}).dropna(how="all")
    out["var_pct"] = out.apply(lambda r: calculate_yoy(r["actual"], r["anterior"]), axis=1)
    if not out.empty:
        out["plaza"] = [config.UNIDADES[u]["nombre"] for u in out.index]
    return out


def serie_trafico_mensual(modelo: ModeloARCO, tipo: str, anios: list[int],
                          unidades: list[str] | None = None) -> pd.DataFrame:
    """Serie mensual agregada por año, para lectura de tendencia y estacionalidad."""
    unidades = filtrar_unidades(modelo, unidades)
    t = modelo.trafico
    df = t[(t["tipo"] == tipo) & (t["anio"].isin(anios)) & (t["unidad"].isin(unidades))]
    return df.pivot_table(index="mes", columns="anio", values="valor", aggfunc="sum")


# -------------------------------------------------------------- cartera ----

def dias_cartera(saldo: float, facturacion_acum: float, meses: int) -> float | None:
    """
    Días cartera = saldo / facturación acumulada × (30 × meses transcurridos).
    Replica el cálculo del libro de cobranza de ARCO.
    """
    if not facturacion_acum:
        return None
    return saldo / facturacion_acum * DIAS_MES * meses


def cartera_resumen(modelo: ModeloARCO, unidades: list[str] | None = None) -> pd.DataFrame:
    """Saldo actual, variación vs mes anterior, días cartera y facturación acumulada."""
    unidades = filtrar_unidades(modelo, unidades)
    h = modelo.cartera_hist
    act = h[(h["anio"] == modelo.anio) & (h["mes"] == modelo.mes)].set_index("unidad")["saldo"]

    if modelo.mes == 1:
        prev = h[(h["anio"] == modelo.anio - 1) & (h["mes"] == 12)].set_index("unidad")["saldo"]
    else:
        prev = h[(h["anio"] == modelo.anio) & (h["mes"] == modelo.mes - 1)].set_index("unidad")["saldo"]

    fact = modelo.cartera_kpi.set_index("unidad")["facturacion_acum"]
    idx = [u for u in config.ORDEN_UNIDADES if u in unidades and u in act.index]
    out = pd.DataFrame(index=idx)
    out["plaza"] = [config.UNIDADES[u]["nombre"] for u in idx]
    out["ciudad"] = [config.UNIDADES[u]["ciudad"] for u in idx]
    out["saldo"] = act.reindex(idx)
    out["saldo_prev"] = prev.reindex(idx)
    out["var_mes_pct"] = out.apply(
        lambda r: calculate_variance(r["saldo"], r["saldo_prev"])["pct"], axis=1)
    out["facturacion_acum"] = fact.reindex(idx)
    out["dias_cartera"] = out.apply(
        lambda r: dias_cartera(r["saldo"], r["facturacion_acum"], modelo.mes), axis=1)
    return out


def cartera_top_clientes(modelo: ModeloARCO, unidades: list[str] | None = None,
                         n: int = 5) -> pd.DataFrame:
    """Mayores deudores del periodo, con su peso dentro de la cartera filtrada."""
    unidades = filtrar_unidades(modelo, unidades)
    d = modelo.cartera_clientes
    df = d[(d["anio"] == modelo.anio) & (d["mes"] == modelo.mes)
           & (d["unidad"].isin(unidades))]
    if df.empty:
        return df
    agg = (df.groupby(["cliente", "unidad"], as_index=False)["saldo"].sum()
             .nlargest(n, "saldo"))
    total = df["saldo"].sum()
    agg["participacion"] = agg["saldo"] / total if total else np.nan
    agg["plaza"] = agg["unidad"].map(lambda u: config.UNIDADES[u]["nombre"])
    return agg[["cliente", "plaza", "saldo", "participacion"]]


def serie_cartera(modelo: ModeloARCO, unidades: list[str] | None = None) -> pd.DataFrame:
    """Serie mensual de cartera del portafolio filtrado."""
    unidades = filtrar_unidades(modelo, unidades)
    h = modelo.cartera_hist[modelo.cartera_hist["unidad"].isin(unidades)]
    out = h.groupby(["anio", "mes"], as_index=False)["saldo"].sum()
    out["periodo"] = out.apply(
        lambda r: f"{config.MESES_ABR[int(r['mes']) - 1]} {int(r['anio']) % 100:02d}", axis=1)
    return out.sort_values(["anio", "mes"])


# ------------------------------------------------ ocupación y superficie ----

def ocupacion_resumen(modelo: ModeloARCO, unidades: list[str] | None = None,
                      acumulado: bool = False) -> pd.DataFrame:
    """
    Ocupación por unidad con la superficie que hay detrás y su valor económico.

    Además del porcentaje, devuelve la renta mínima estimada en riesgo por los
    m² disponibles: el porcentaje solo dice qué tan llena está la plaza, no
    cuánto cuesta el espacio vacío.
    """
    unidades = filtrar_unidades(modelo, unidades)
    if modelo.ocupacion.empty:
        return pd.DataFrame(columns=["plaza", "ciudad", "gla_total", "gla_ocupada",
                                     "gla_vacante", "ocupacion_pct",
                                     "renta_por_m2", "renta_en_riesgo"])

    alcance = "acum" if acumulado else "mes"
    ocu = modelo.ocupacion[modelo.ocupacion["unidad"].isin(unidades)].set_index("unidad")
    renta = (modelo.pl[(modelo.pl["concepto"] == "Renta Mínima")
                       & (modelo.pl["categoria"] == "ingreso")
                       & (modelo.pl["alcance"] == alcance)
                       & (modelo.pl["escenario"] == "real_actual")]
             .groupby("unidad")["valor"].sum())

    idx = [u for u in config.ORDEN_UNIDADES if u in ocu.index]
    out = ocu.reindex(idx).copy()
    out.insert(0, "ciudad", [config.UNIDADES[u]["ciudad"] for u in idx])
    out.insert(0, "plaza", [config.UNIDADES[u]["nombre"] for u in idx])
    out["renta_por_m2"] = renta.reindex(idx) / out["gla_ocupada"].replace(0, np.nan)
    out["renta_en_riesgo"] = out["renta_por_m2"] * out["gla_vacante"]
    return out


def ocupacion_portafolio(modelo: ModeloARCO, unidades: list[str] | None = None) -> dict:
    """Ocupación consolidada ponderada por GLA, no promedio simple entre plazas."""
    resumen = ocupacion_resumen(modelo, unidades)
    if resumen.empty:
        return {"ocupacion_pct": None, "gla_total": None, "gla_vacante": None,
                "renta_en_riesgo": None, "plazas": 0}
    gla = resumen["gla_total"].sum()
    return {
        "ocupacion_pct": resumen["gla_ocupada"].sum() / gla if gla else None,
        "gla_total": gla,
        "gla_ocupada": resumen["gla_ocupada"].sum(),
        "gla_vacante": resumen["gla_vacante"].sum(),
        "renta_en_riesgo": resumen["renta_en_riesgo"].sum(),
        "plazas": len(resumen),
    }


def indicadores_por_m2(modelo: ModeloARCO, unidades: list[str] | None = None,
                       acumulado: bool = False) -> pd.DataFrame:
    """
    Ingreso, gasto y UAIIDA por metro cuadrado de GLA.

    Es la comparación que el porcentaje de ocupación no permite: dos plazas
    pueden estar igual de llenas y rendir muy distinto por metro.
    """
    alcance = "acum" if acumulado else "mes"
    resumen = ocupacion_resumen(modelo, unidades, acumulado)
    if resumen.empty:
        return resumen

    ing = pl_por_unidad(modelo, "Total Ingresos Netos", alcance, unidades)
    gas = pl_por_unidad(modelo, "Gastos de Operación", alcance, unidades)
    ua = pl_por_unidad(modelo, "UAIIDA Ajustado", alcance, unidades)

    idx = [u for u in resumen.index if u in ing.index]
    out = resumen.loc[idx, ["plaza", "ciudad", "gla_total", "gla_vacante",
                            "ocupacion_pct", "renta_en_riesgo"]].copy()
    gla_ocupada = resumen.loc[idx, "gla_ocupada"].replace(0, np.nan)
    out["ingreso_por_m2"] = ing.loc[idx, "real"] / gla_ocupada
    out["gasto_por_m2"] = gas.loc[idx, "real"] / gla_ocupada
    out["uaiida_por_m2"] = ua.loc[idx, "real"] / gla_ocupada
    return out


# ------------------------------------------- indicadores por visita ----

def ratios_normalizados(modelo: ModeloARCO, unidades: list[str] | None = None,
                        acumulado: bool = False) -> pd.DataFrame:
    """
    Indicadores por visita, que permiten comparar plazas de tamaños distintos.
    Sólo se calculan cuando existe un denominador válido.
    """
    alcance = "acum" if acumulado else "mes"
    ing = pl_por_unidad(modelo, "Total Ingresos Netos", alcance, unidades)
    gas = pl_por_unidad(modelo, "Gastos de Operación", alcance, unidades)
    afl = trafico_periodo(modelo, "afluencia", modelo.anio, modelo.mes, unidades, acumulado)
    afo = trafico_periodo(modelo, "aforo", modelo.anio, modelo.mes, unidades, acumulado)

    out = pd.DataFrame(index=ing.index)
    out["plaza"] = ing["plaza"]
    out["afluencia"] = afl.reindex(ing.index)
    out["aforo"] = afo.reindex(ing.index)
    out["ingreso_por_visita"] = ing["real"] / out["afluencia"].replace(0, np.nan)
    out["gasto_por_visita"] = gas["real"] / out["afluencia"].replace(0, np.nan)
    out["ingreso_por_vehiculo"] = ing["real"] / out["aforo"].replace(0, np.nan)
    return out
