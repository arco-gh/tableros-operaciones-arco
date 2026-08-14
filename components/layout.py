"""Capa 3 — Estructura visual común a todas las pestañas."""

from __future__ import annotations

import streamlit as st

from src import config, metrics


def configurar_pagina() -> None:
    st.set_page_config(
        page_title="Tablero Ejecutivo · ARCO",
        page_icon="▦",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def cargar_estilos() -> None:
    """
    Inyecta la hoja de estilos institucional.

    Se usa `st.html` y no `st.markdown`: este último procesa el contenido como
    Markdown, donde una línea en blanco cierra el bloque HTML. Con una hoja de
    estilos que separa secciones con líneas vacías, todo lo posterior a la
    primera se imprimiría como texto en la página en lugar de aplicarse.

    Si el archivo no llegó al servidor —caso frecuente cuando el proyecto se
    sube por arrastre en el navegador— el tablero funciona pero se ve sin
    formato. Se avisa de forma explícita en lugar de fallar en silencio.
    """
    ruta = config.ASSETS / "styles.css"
    if not ruta.exists():
        st.warning(
            f"No se encontró la hoja de estilos en `{ruta}`. El tablero funciona, "
            "pero se muestra sin formato institucional. Verifique que la carpeta "
            "`assets/` se haya desplegado completa."
        )
        css = ""
    else:
        css = ruta.read_text(encoding="utf-8")

    st.html(
        "<link href='https://fonts.googleapis.com/css2?"
        "family=Barlow:wght@400;500;600;700;800&display=swap' rel='stylesheet'>"
        f"<style>{css}</style>"
    )


def _badge(etiqueta: str, valor: str, tono: str = "") -> str:
    clase = f" {tono}" if tono else ""
    return (f"<div class='arco-badge'><div class='lbl'>{etiqueta}</div>"
            f"<div class='val{clase}'>{valor}</div></div>")


def encabezado(modelo, kpis_mes: dict, kpis_acum: dict, alcance: str) -> None:
    """Encabezado con el pulso del portafolio bajo el filtro vigente."""
    k = kpis_mes if alcance == "mes" else kpis_acum
    periodo = modelo.periodo_label if alcance == "mes" else modelo.acumulado_label

    def tono(v, invertir=False):
        if v is None:
            return ""
        bueno = (v <= 0) if invertir else (v >= 0)
        return "pos" if bueno else "neg"

    badges = "".join([
        _badge("Ingresos netos", metrics.format_millions(k["ingresos"]["real"]),
               tono(k["ingresos"]["var_ly"])),
        _badge("vs año anterior", metrics.format_variation(k["ingresos"]["var_ly"]),
               tono(k["ingresos"]["var_ly"])),
        _badge("UAIIDA ajustado", metrics.format_millions(k["uaiida"]["real"]),
               tono(k["uaiida"]["var_ly"])),
        _badge("Margen UAIIDA", metrics.format_percentage(k["margen"]["real"]),
               tono(k["margen"]["delta_ly_pp"])),
        _badge("vs presupuesto", metrics.format_variation(k["uaiida"]["var_ppto"]),
               tono(k["uaiida"]["var_ppto"])),
    ])

    chip = ""
    if config.ENTORNO:
        clase = "env-chip" if config.entorno_es_oficial() else "env-chip alerta"
        chip = f"<span class='{clase}'>{config.ENTORNO}</span>"

    st.html(
        f"""
        <div class="arco-header">
          <div>
            <div class="eyebrow">Tablero ejecutivo · Seguimiento y diagnóstico {chip}</div>
            <h1>ARCO Áreas Comerciales</h1>
            <div class="period">{periodo} · Última actualización de datos:
            {modelo.periodo_label}</div>
          </div>
          <div class="badges">{badges}</div>
        </div>
        """,
    )


def titulo_seccion(texto: str) -> None:
    st.html(f"<div class='arco-section'>{texto}</div>")


def nota(texto: str) -> None:
    st.html(f"<div class='note-box'>{texto}</div>")


def pill(texto: str, tono: str) -> str:
    return f"<span class='pill pill-{tono}'>{texto}</span>"
