"""
Capa 2 — Hallazgos automáticos.

Genera entre 3 y 7 frases de diagnóstico a partir de los datos ya filtrados.
Ningún hallazgo está escrito a mano en la interfaz: todos se derivan aquí, de
modo que cambiar el filtro o el mes cambia el texto.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import analytics, config, metrics
from .data_model import ModeloARCO


def _hallazgo(prioridad: int, texto: str, tono: str = "neutral") -> dict:
    return {"prioridad": prioridad, "texto": texto, "tono": tono}


def _concentracion_desviacion(modelo, unidades, alcance, periodo) -> list[dict]:
    """
    Atribuye la desviación consolidada contra presupuesto a la unidad que más la
    explica. Cuando las desviaciones individuales se compensan entre sí, el
    porcentaje sobre el neto pierde sentido y se reporta el importe absoluto.
    """
    salida = []
    for concepto, sujeto, malo_si_positivo in (
        ("Gastos de Operación", "El gasto de operación", True),
        ("Total Ingresos Netos", "Los ingresos netos", False),
    ):
        df = metrics.pl_por_unidad(modelo, concepto, alcance, unidades)
        if df.empty or df["ppto"].sum() == 0:
            continue
        total = df["real"].sum() - df["ppto"].sum()
        if abs(total) < 1:
            continue

        contrib = analytics.contribucion_desviacion(df, "real", "ppto", top=3)
        mismo_signo = contrib[np.sign(contrib["desviacion"]) == np.sign(total)]
        if mismo_signo.empty:
            continue
        lider = mismo_signo.iloc[0]
        cuota = lider["contribucion_pct"]

        if pd.notna(cuota) and 0 < cuota <= 1:
            atribucion = (f"{lider['plaza']} explica "
                          f"{metrics.format_percentage(cuota)} de esa desviación "
                          f"({metrics.format_millions(lider['desviacion'])})")
        else:
            atribucion = (f"la mayor desviación individual es {lider['plaza']} con "
                          f"{metrics.format_millions(lider['desviacion'])}, parcialmente "
                          f"compensada por otras unidades")

        adverso = (total > 0) == malo_si_positivo
        salida.append(_hallazgo(
            1 if adverso else 3,
            f"{sujeto} cierran {periodo} {metrics.format_millions(abs(total))} "
            f"{'sobre' if total > 0 else 'bajo'} presupuesto; {atribucion}.",
            "malo" if adverso else "bueno"))
    return salida


def _rentabilidad(modelo, unidades, alcance, periodo) -> list[dict]:
    kpis = metrics.kpis_portafolio(modelo, alcance, unidades)
    salida = []
    m = kpis["margen"]
    if m["real"] is not None and m["delta_ly_pp"] is not None:
        direccion = "mejora" if m["delta_ly_pp"] >= 0 else "se contrae"
        salida.append(_hallazgo(
            2 if abs(m["delta_ly_pp"]) >= 1 else 5,
            f"El margen UAIIDA del portafolio se ubica en "
            f"{metrics.format_percentage(m['real'])} en {periodo} y {direccion} "
            f"{abs(m['delta_ly_pp']):.1f} puntos porcentuales frente al año anterior.",
            "bueno" if m["delta_ly_pp"] >= 0 else "malo"))

    ing = kpis["ingresos"]
    if ing["var_ly"] is not None:
        salida.append(_hallazgo(
            4,
            f"Los ingresos netos suman {metrics.format_millions(ing['real'])} "
            f"({metrics.format_variation(ing['var_ly'])} vs año anterior y "
            f"{metrics.format_variation(ing['var_ppto'])} vs presupuesto).",
            "bueno" if ing["var_ly"] >= 0 else "malo"))
    return salida


def _extremos_unidad(modelo, unidades, alcance) -> list[dict]:
    ua = metrics.pl_por_unidad(modelo, "UAIIDA Ajustado", alcance, unidades)
    if ua.empty:
        return []
    ua = ua.copy()
    ua["var_ly"] = ua.apply(lambda r: metrics.calculate_yoy(r["real"], r["ly"]), axis=1)
    validos = ua.dropna(subset=["var_ly"])
    if validos.empty:
        return []
    peor = validos.nsmallest(1, "var_ly").iloc[0]
    mejor = validos.nlargest(1, "var_ly").iloc[0]
    salida = []
    if peor["var_ly"] < 0:
        salida.append(_hallazgo(
            2,
            f"{peor['plaza']} presenta la mayor caída de UAIIDA del portafolio: "
            f"{metrics.format_variation(peor['var_ly'])} vs año anterior "
            f"({metrics.format_millions(peor['real'] - peor['ly'])}).",
            "malo"))
    if mejor["var_ly"] > 0.10:
        salida.append(_hallazgo(
            5,
            f"{mejor['plaza']} lidera el crecimiento con "
            f"{metrics.format_variation(mejor['var_ly'])} de UAIIDA vs año anterior.",
            "bueno"))
    return salida


def _cartera(modelo, unidades) -> list[dict]:
    resumen = metrics.cartera_resumen(modelo, unidades)
    if resumen.empty:
        return []
    salida = []
    saldo_total = resumen["saldo"].sum()
    prev_total = resumen["saldo_prev"].sum()
    var = metrics.calculate_variance(saldo_total, prev_total)

    if var["pct"] is not None:
        crecimiento = resumen.assign(delta=resumen["saldo"] - resumen["saldo_prev"])
        top = crecimiento.nlargest(2, "delta")
        nombres = " y ".join(top["plaza"].tolist())
        peso = top["delta"].sum() / (saldo_total - prev_total) if saldo_total != prev_total else np.nan
        detalle = ""
        if not pd.isna(peso) and peso > 0:
            detalle = (f" y se concentra principalmente en {nombres} "
                       f"({metrics.format_percentage(peso)} del incremento)")
        salida.append(_hallazgo(
            1 if var["pct"] > 0.05 else 4,
            f"La cartera del portafolio filtrado asciende a "
            f"{metrics.format_millions(saldo_total)}, "
            f"{metrics.format_variation(var['pct'])} respecto al mes anterior{detalle}.",
            "malo" if var["pct"] > 0 else "bueno"))

    criticas = resumen[resumen["dias_cartera"] >= config.UMBRALES["dc_critico"]]
    if not criticas.empty:
        salida.append(_hallazgo(
            1,
            f"{len(criticas)} unidad(es) superan {config.UMBRALES['dc_critico']:.0f} días "
            f"cartera: {', '.join(criticas['plaza'].tolist())}.",
            "malo"))
    return salida


def _trafico(modelo, unidades) -> list[dict]:
    salida = []
    for tipo, etiqueta in (("afluencia", "afluencia peatonal"), ("aforo", "aforo vehicular")):
        comp = metrics.trafico_comparativo(modelo, tipo, unidades, acumulado=True)
        if comp.empty:
            continue
        total_act, total_ant = comp["actual"].sum(), comp["anterior"].sum()
        var = metrics.calculate_yoy(total_act, total_ant)
        if var is None:
            continue
        negativas = comp[comp["var_pct"] < 0]
        detalle = ""
        if len(negativas):
            detalle = (f"; {len(negativas)} de {len(comp)} unidades están por debajo "
                       f"del año anterior")
        salida.append(_hallazgo(
            3 if abs(var) >= 0.03 else 6,
            f"El acumulado de {etiqueta} del portafolio es "
            f"{metrics.format_number(total_act)} visitas, "
            f"{metrics.format_variation(var)} vs mismo periodo del año anterior{detalle}.",
            "bueno" if var >= 0 else "malo"))
    return salida


def _tendencia_persistente(modelo, unidades) -> list[dict]:
    tend = analytics.tendencia_por_unidad(modelo, "afluencia", unidades)
    if tend.empty:
        return []
    persistentes = tend[(tend["meses_negativos"] == tend["meses_evaluados"])
                        & (tend["meses_evaluados"] >= 3)]
    if persistentes.empty:
        return []
    return [_hallazgo(
        2,
        f"{len(persistentes)} plaza(s) llevan {int(persistentes['meses_evaluados'].max())} "
        f"meses consecutivos con afluencia por debajo del año anterior: "
        f"{', '.join(persistentes['plaza'].tolist())}.",
        "malo")]


def _ocupacion(modelo, unidades, periodo) -> list[dict]:
    resumen = metrics.ocupacion_resumen(modelo, unidades)
    if resumen.empty:
        return []

    salida = []
    port = metrics.ocupacion_portafolio(modelo, unidades)
    bajo_objetivo = resumen[resumen["ocupacion_pct"] < config.UMBRALES["ocupacion_objetivo"]]

    detalle = ""
    if not bajo_objetivo.empty:
        detalle = (f"; {len(bajo_objetivo)} de {len(resumen)} plazas están por debajo "
                   f"del objetivo de "
                   f"{metrics.format_percentage(config.UMBRALES['ocupacion_objetivo'])}")
    salida.append(_hallazgo(
        2 if not bajo_objetivo.empty else 5,
        f"La ocupación del portafolio filtrado es "
        f"{metrics.format_percentage(port['ocupacion_pct'])} sobre "
        f"{metrics.format_number(port['gla_total'])} m² de GLA, con "
        f"{metrics.format_number(port['gla_vacante'])} m² disponibles{detalle}.",
        "malo" if not bajo_objetivo.empty else "bueno"))

    # Dónde duele el espacio vacío, que no siempre es donde el porcentaje es peor.
    con_riesgo = resumen.dropna(subset=["renta_en_riesgo"])
    con_riesgo = con_riesgo[con_riesgo["renta_en_riesgo"] > 0]
    if not con_riesgo.empty:
        total_riesgo = con_riesgo["renta_en_riesgo"].sum()
        lider = con_riesgo.nlargest(1, "renta_en_riesgo").iloc[0]
        peor_pct = resumen.nsmallest(1, "ocupacion_pct").iloc[0]
        matiz = ""
        if lider["plaza"] != peor_pct["plaza"]:
            matiz = (f", aunque la ocupación más baja está en {peor_pct['plaza']} "
                     f"({metrics.format_percentage(peor_pct['ocupacion_pct'])})")
        salida.append(_hallazgo(
            1,
            f"La superficie vacante representa del orden de "
            f"{metrics.format_millions(total_riesgo)} mensuales de renta no colocada; "
            f"{lider['plaza']} concentra "
            f"{metrics.format_percentage(lider['renta_en_riesgo'] / total_riesgo)} "
            f"de ese importe{matiz}.",
            "malo"))
    return salida


def generate_insights(modelo: ModeloARCO, unidades: list[str] | None = None,
                      alcance: str = "mes", maximo: int = 7) -> list[dict]:
    """Devuelve entre 3 y 7 hallazgos priorizados sobre los datos filtrados."""
    periodo = modelo.periodo_label if alcance == "mes" else modelo.acumulado_label
    hallazgos: list[dict] = []
    hallazgos += _concentracion_desviacion(modelo, unidades, alcance, periodo)
    hallazgos += _rentabilidad(modelo, unidades, alcance, periodo)
    hallazgos += _extremos_unidad(modelo, unidades, alcance)
    hallazgos += _cartera(modelo, unidades)
    hallazgos += _trafico(modelo, unidades)
    hallazgos += _ocupacion(modelo, unidades, periodo)
    hallazgos += _tendencia_persistente(modelo, unidades)

    vistos, unicos = set(), []
    for h in sorted(hallazgos, key=lambda x: x["prioridad"]):
        if h["texto"] in vistos:
            continue
        vistos.add(h["texto"])
        unicos.append(h)
    return unicos[:maximo]
