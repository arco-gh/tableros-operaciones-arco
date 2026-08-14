"""
Capa 2 — Motor de alertas.

Evalúa reglas sobre los datos ya filtrados y devuelve una tabla homogénea:

    severity · kpi · plaza · period · message · value · reference

Las alertas se ordenan por severidad y por impacto económico, no por orden de
evaluación, para que la pantalla muestre primero lo que más pesa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import analytics, config, metrics
from .data_model import ModeloARCO

ORDEN_SEVERIDAD = {s: i for i, s in enumerate(config.SEVERIDADES)}


def _alerta(severity, kpi, plaza, period, message, value=None, reference=None,
            impacto=0.0) -> dict:
    return {"severity": severity, "kpi": kpi, "plaza": plaza, "period": period,
            "message": message, "value": value, "reference": reference,
            "impacto": abs(impacto or 0.0)}


def _sev_por_desviacion(pct: float | None, critico: float, alto: float) -> str:
    if pct is None:
        return "LOW"
    a = abs(pct)
    if a >= critico:
        return "CRITICAL"
    if a >= alto:
        return "HIGH"
    return "MEDIUM"


def _reglas_presupuesto(modelo, unidades, alcance, periodo) -> list[dict]:
    u = config.UMBRALES
    salida = []

    ing = metrics.pl_por_unidad(modelo, "Total Ingresos Netos", alcance, unidades)
    for clave, fila in ing.iterrows():
        if not fila["ppto"]:
            continue
        pct = fila["real"] / fila["ppto"] - 1
        if pct >= -u["desviacion_alta"]:
            continue
        salida.append(_alerta(
            _sev_por_desviacion(pct, u["desviacion_critica"], u["desviacion_alta"]),
            "Ingresos vs presupuesto", fila["plaza"], periodo,
            f"Ingresos {metrics.format_variation(pct)} respecto al presupuesto "
            f"({metrics.format_millions(fila['real'] - fila['ppto'])}).",
            fila["real"], fila["ppto"], fila["real"] - fila["ppto"]))

    gas = metrics.pl_por_unidad(modelo, "Gastos de Operación", alcance, unidades)
    for clave, fila in gas.iterrows():
        if not fila["ppto"]:
            continue
        pct = fila["real"] / fila["ppto"] - 1
        if pct <= u["desviacion_alta"]:
            continue
        salida.append(_alerta(
            _sev_por_desviacion(pct, u["desviacion_critica"], u["desviacion_alta"]),
            "Gasto sobre presupuesto", fila["plaza"], periodo,
            f"Gasto de operación {metrics.format_variation(pct)} sobre presupuesto "
            f"({metrics.format_millions(fila['real'] - fila['ppto'])} adicionales).",
            fila["real"], fila["ppto"], fila["real"] - fila["ppto"]))
    return salida


def _reglas_rentabilidad(modelo, unidades, alcance, periodo) -> list[dict]:
    u = config.UMBRALES
    salida = []
    ing = metrics.pl_por_unidad(modelo, "Total Ingresos Netos", alcance, unidades)
    ua = metrics.pl_por_unidad(modelo, "UAIIDA Ajustado", alcance, unidades)

    for clave in ing.index:
        real_i, ly_i = ing.loc[clave, "real"], ing.loc[clave, "ly"]
        real_u, ly_u = ua.loc[clave, "real"], ua.loc[clave, "ly"]
        plaza = ing.loc[clave, "plaza"]

        m_act = real_u / real_i if real_i else None
        m_ly = ly_u / ly_i if ly_i else None
        if m_act is not None and m_ly is not None:
            caida_pp = (m_ly - m_act) * 100
            if caida_pp >= u["margen_caida_pp"]:
                salida.append(_alerta(
                    "CRITICAL" if caida_pp >= 2 * u["margen_caida_pp"] else "HIGH",
                    "Margen UAIIDA", plaza, periodo,
                    f"El margen UAIIDA cae {caida_pp:.1f} puntos porcentuales vs año "
                    f"anterior ({metrics.format_percentage(m_ly)} → "
                    f"{metrics.format_percentage(m_act)}).",
                    m_act, m_ly, real_u - ly_u))

        var_i = metrics.calculate_yoy(real_i, ly_i)
        var_u = metrics.calculate_yoy(real_u, ly_u)
        if var_i is not None and var_u is not None and var_i < 0 and var_u < 0:
            salida.append(_alerta(
                "CRITICAL", "Ingresos y UAIIDA", plaza, periodo,
                f"Ingresos ({metrics.format_variation(var_i)}) y UAIIDA "
                f"({metrics.format_variation(var_u)}) caen simultáneamente vs año anterior.",
                real_u, ly_u, real_u - ly_u))
    return salida


def _reglas_cartera(modelo, unidades, periodo) -> list[dict]:
    u = config.UMBRALES
    salida = []
    resumen = metrics.cartera_resumen(modelo, unidades)

    for clave, fila in resumen.iterrows():
        dc = fila["dias_cartera"]
        if dc is not None and not pd.isna(dc):
            if dc >= u["dc_critico"]:
                salida.append(_alerta(
                    "CRITICAL", "Días cartera", fila["plaza"], periodo,
                    f"Días cartera en {dc:.1f}, muy por encima del objetivo de "
                    f"{u['dc_objetivo']:.0f} días.",
                    dc, u["dc_objetivo"], fila["saldo"]))
            elif dc >= u["dc_objetivo"]:
                salida.append(_alerta(
                    "MEDIUM", "Días cartera", fila["plaza"], periodo,
                    f"Días cartera en {dc:.1f}, por encima del objetivo de "
                    f"{u['dc_objetivo']:.0f} días.",
                    dc, u["dc_objetivo"], fila["saldo"]))

        var = fila["var_mes_pct"]
        if var is not None and not pd.isna(var) and var >= 0.15:
            salida.append(_alerta(
                "HIGH" if var < 0.35 else "CRITICAL", "Cartera vencida",
                fila["plaza"], periodo,
                f"La cartera crece {metrics.format_variation(var)} respecto al mes "
                f"anterior ({metrics.format_millions(fila['saldo'] - fila['saldo_prev'])}).",
                fila["saldo"], fila["saldo_prev"], fila["saldo"] - fila["saldo_prev"]))

    # Concentración de riesgo en un solo cliente.
    top = metrics.cartera_top_clientes(modelo, unidades, n=3)
    if not top.empty:
        for _, fila in top.iterrows():
            if fila["participacion"] >= u["concentracion_cliente"]:
                salida.append(_alerta(
                    "HIGH", "Concentración de riesgo", fila["plaza"], periodo,
                    f"{fila['cliente'].title()} concentra "
                    f"{metrics.format_percentage(fila['participacion'])} de la cartera "
                    f"del portafolio filtrado.",
                    fila["saldo"], None, fila["saldo"]))

    deterioro = analytics.deterioro_cartera(modelo, unidades)
    for _, fila in deterioro.iterrows():
        if fila["meses_al_alza"] >= config.UMBRALES["periodos_deterioro"]:
            salida.append(_alerta(
                "HIGH", "Deterioro sostenido", fila["plaza"], periodo,
                f"La cartera acumula {int(fila['meses_al_alza'])} meses consecutivos "
                f"al alza (saldo actual {metrics.format_millions(fila['saldo_actual'])}).",
                fila["saldo_actual"], None, fila["saldo_actual"]))
    return salida


def _reglas_trafico(modelo, unidades, periodo) -> list[dict]:
    salida = []
    for tipo, etiqueta in (("afluencia", "Afluencia"), ("aforo", "Aforo")):
        tend = analytics.tendencia_por_unidad(modelo, tipo, unidades)
        for _, fila in tend.iterrows():
            if fila["meses_negativos"] == fila["meses_evaluados"] and fila["meses_evaluados"] >= 3:
                salida.append(_alerta(
                    "HIGH", etiqueta, fila["plaza"], periodo,
                    f"{etiqueta} por debajo del año anterior en los "
                    f"{int(fila['meses_evaluados'])} meses evaluados "
                    f"(promedio {metrics.format_variation(fila['var_promedio'])}).",
                    fila["var_promedio"], 0, 0))
            elif fila["deterioro_consecutivo"] >= config.UMBRALES["periodos_deterioro"]:
                salida.append(_alerta(
                    "MEDIUM", etiqueta, fila["plaza"], periodo,
                    f"{etiqueta} se deteriora {int(fila['deterioro_consecutivo'])} meses "
                    "consecutivos frente al año anterior.",
                    fila["var_promedio"], 0, 0))
    return salida


def _reglas_ocupacion(modelo, unidades, periodo) -> list[dict]:
    u = config.UMBRALES
    salida = []
    resumen = metrics.ocupacion_resumen(modelo, unidades)
    if resumen.empty:
        return salida

    for _, fila in resumen.iterrows():
        pct = fila["ocupacion_pct"]
        if pd.isna(pct) or pct >= u["ocupacion_objetivo"]:
            continue
        critica = pct < u["ocupacion_critica"]
        riesgo = fila["renta_en_riesgo"]
        detalle = ""
        if pd.notna(riesgo) and riesgo > 0:
            detalle = (f" Los {metrics.format_number(fila['gla_vacante'])} m² disponibles "
                       f"representan del orden de {metrics.format_millions(riesgo)} "
                       f"mensuales de renta no colocada.")
        salida.append(_alerta(
            "CRITICAL" if critica else "MEDIUM", "Ocupación", fila["plaza"], periodo,
            f"Ocupación en {metrics.format_percentage(pct)}, por debajo del objetivo de "
            f"{metrics.format_percentage(u['ocupacion_objetivo'])}.{detalle}",
            pct, u["ocupacion_objetivo"], riesgo if pd.notna(riesgo) else 0))
    return salida


def _reglas_datos(modelo, unidades, periodo) -> list[dict]:
    """Falta de información: se reporta como hallazgo, no se oculta."""
    salida = []
    sin_afluencia = [config.UNIDADES[u]["nombre"] for u in metrics.filtrar_unidades(modelo, unidades)
                     if not config.UNIDADES[u]["cod_afluencia"]]
    if sin_afluencia:
        salida.append(_alerta(
            "LOW", "Cobertura de datos", ", ".join(sin_afluencia), periodo,
            "Estas unidades no reportan afluencia peatonal; sus indicadores por "
            "visita no pueden calcularse.", None, None, 0))
    if modelo.ocupacion.empty:
        salida.append(_alerta(
            "LOW", "Cobertura de datos", "Portafolio", periodo,
            "No hay fuente de ocupación (% de área rentable ocupada) en data/raw. "
            "Es un dato distinto de afluencia y aforo y debe solicitarse a "
            "Comercialización.", None, None, 0))
    else:
        cubiertas = set(modelo.ocupacion["unidad"])
        faltantes = [config.UNIDADES[u]["nombre"]
                     for u in metrics.filtrar_unidades(modelo, unidades)
                     if u not in cubiertas]
        if faltantes:
            salida.append(_alerta(
                "LOW", "Cobertura de datos", ", ".join(faltantes), periodo,
                "Estas unidades no aparecen en el archivo de ocupación; su GLA e "
                "indicadores por m² no pueden calcularse.", None, None, 0))
    return salida


def build_alerts(modelo: ModeloARCO, unidades: list[str] | None = None,
                 alcance: str = "mes", limite: int | None = 12) -> pd.DataFrame:
    """Evalúa todas las reglas y devuelve las alertas priorizadas."""
    periodo = modelo.periodo_label if alcance == "mes" else modelo.acumulado_label
    reglas = []
    reglas += _reglas_presupuesto(modelo, unidades, alcance, periodo)
    reglas += _reglas_rentabilidad(modelo, unidades, alcance, periodo)
    reglas += _reglas_cartera(modelo, unidades, periodo)
    reglas += _reglas_trafico(modelo, unidades, periodo)
    reglas += _reglas_ocupacion(modelo, unidades, periodo)
    reglas += _reglas_datos(modelo, unidades, periodo)

    if not reglas:
        return pd.DataFrame(columns=["severity", "kpi", "plaza", "period",
                                     "message", "value", "reference", "impacto"])

    df = pd.DataFrame(reglas)
    df["_orden"] = df["severity"].map(ORDEN_SEVERIDAD)
    df = df.sort_values(["_orden", "impacto"], ascending=[True, False]).drop(columns="_orden")
    return df.head(limite) if limite else df


def conteo_por_severidad(alertas: pd.DataFrame) -> dict:
    if alertas.empty:
        return {s: 0 for s in config.SEVERIDADES}
    conteo = alertas["severity"].value_counts().to_dict()
    return {s: int(conteo.get(s, 0)) for s in config.SEVERIDADES}
