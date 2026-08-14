"""Capa 3 — Tarjetas de indicador, alertas y hallazgos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config, metrics


def _clase_delta(valor, invertir: bool) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "neu"
    if abs(valor) < 0.001:
        return "neu"
    bueno = (valor <= 0) if invertir else (valor >= 0)
    return "pos" if bueno else "neg"


def create_kpi_card(etiqueta: str, valor: str, referencia: str = "",
                    delta=None, delta_texto: str = "", invertir: bool = False) -> str:
    """HTML de una tarjeta. Se devuelve como cadena para poder componer rejillas."""
    ref = f"<div class='ref'>{referencia}</div>" if referencia else ""
    if delta_texto:
        clase = _clase_delta(delta, invertir)
        dlt = f"<div class='delta {clase}'>{delta_texto}</div>"
    else:
        dlt = ""
    return (f"<div class='kpi-card'><div class='lbl'>{etiqueta}</div>"
            f"<div class='val'>{valor}</div>{ref}{dlt}</div>")


def rejilla_kpis(tarjetas: list[str], columnas: int = 4) -> None:
    cols = st.columns(columnas, gap="small")
    for i, html in enumerate(tarjetas):
        with cols[i % columnas]:
            st.markdown(html, unsafe_allow_html=True)


def tarjetas_financieras(kpis: dict, comparativo: str = "ly") -> list[str]:
    """
    Bloque estándar de ingresos, gastos, UAIIDA y margen.

    `comparativo` decide contra qué se lee la variación: año anterior o presupuesto.
    """
    es_ly = comparativo == "ly"
    ref_lbl = "año anterior" if es_ly else "presupuesto"

    def bloque(clave, etiqueta, invertir=False):
        k = kpis[clave]
        base = k["ly"] if es_ly else k["ppto"]
        var = k["var_ly"] if es_ly else k["var_ppto"]
        return create_kpi_card(
            etiqueta,
            metrics.format_millions(k["real"]),
            f"{ref_lbl.capitalize()}: {metrics.format_millions(base)}",
            var, metrics.format_variation(var), invertir=invertir,
        )

    m = kpis["margen"]
    base_margen = m["ly"] if es_ly else m["ppto"]
    delta_pp = None
    if m["real"] is not None and base_margen is not None:
        delta_pp = (m["real"] - base_margen) * 100

    return [
        bloque("ingresos", "Ingresos netos"),
        bloque("gastos", "Gastos de operación", invertir=True),
        bloque("uaiida", "UAIIDA ajustado"),
        create_kpi_card(
            "Margen UAIIDA",
            metrics.format_percentage(m["real"]),
            f"{ref_lbl.capitalize()}: {metrics.format_percentage(base_margen)}",
            delta_pp,
            f"{'+' if (delta_pp or 0) >= 0 else ''}{delta_pp:.1f} pp" if delta_pp is not None else "",
        ),
    ]


def bloque_alertas(alertas: pd.DataFrame, maximo: int = 8) -> None:
    if alertas.empty:
        st.success("Sin alertas activas para la selección vigente.")
        return
    for _, a in alertas.head(maximo).iterrows():
        st.markdown(
            f"""<div class='alert-row {a["severity"]}'>
                  <div class='meta'>{config.SEVERIDAD_LABEL[a["severity"]]} ·
                  {a["kpi"]} · {a["plaza"]}</div>
                  <div class='msg'>{a["message"]}</div>
                </div>""",
            unsafe_allow_html=True,
        )


def bloque_hallazgos(hallazgos: list[dict]) -> None:
    if not hallazgos:
        st.info("No se identificaron hallazgos relevantes con los filtros actuales.")
        return
    for i, h in enumerate(hallazgos, start=1):
        st.markdown(
            f"""<div class='finding {h["tono"]}'>
                  <div class='rank'>{i}</div>
                  <div class='txt'>{h["texto"]}</div>
                </div>""",
            unsafe_allow_html=True,
        )
