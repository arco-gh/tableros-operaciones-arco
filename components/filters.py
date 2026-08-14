"""
Capa 3 — Filtros globales.

Un único punto de verdad para la selección del usuario. Todas las secciones del
tablero consumen el mismo objeto `Seleccion`, de modo que no puede ocurrir que
una tarjeta muestre el consolidado y una gráfica una sola plaza.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from src import config
from src.data_model import ModeloARCO


@dataclass
class Seleccion:
    unidades: list[str]
    ciudades: list[str]
    alcance: str          # 'mes' | 'acum'
    anios_trafico: list[int]

    @property
    def es_portafolio_completo(self) -> bool:
        return len(self.unidades) == len(config.ORDEN_UNIDADES)

    @property
    def alcance_label(self) -> str:
        return "Mes actual" if self.alcance == "mes" else "Acumulado del año"


def barra_lateral(modelo: ModeloARCO) -> Seleccion:
    st.sidebar.markdown("### Filtros")

    alcance_txt = st.sidebar.radio(
        "Periodo de análisis",
        [f"Mes — {modelo.periodo_label}", f"Acumulado — {modelo.acumulado_label}"],
        help="Define si los indicadores muestran el mes de corte o el acumulado del año.",
    )
    alcance = "mes" if alcance_txt.startswith("Mes") else "acum"

    activas = modelo.unidades_activas
    ciudades_disponibles = sorted({config.UNIDADES[u]["ciudad"] for u in activas})
    ciudades = st.sidebar.multiselect(
        "Ciudad", ciudades_disponibles, default=ciudades_disponibles,
        help="Filtrar por ciudad limita las plazas disponibles abajo.",
    )
    if not ciudades:
        ciudades = ciudades_disponibles

    # Filtro dependiente: la ciudad acota el universo de plazas.
    candidatas = [u for u in activas if config.UNIDADES[u]["ciudad"] in ciudades]
    etiquetas = {u: f"{config.UNIDADES[u]['nombre']} ({u})" for u in candidatas}
    seleccion_plazas = st.sidebar.multiselect(
        "Plaza", list(etiquetas.values()), default=list(etiquetas.values()),
        help="Todas las secciones del tablero responden a esta selección.",
    )
    inverso = {v: k for k, v in etiquetas.items()}
    unidades = [inverso[e] for e in seleccion_plazas] or candidatas

    anios_disponibles = sorted(modelo.trafico["anio"].unique(), reverse=True)
    por_defecto = [a for a in anios_disponibles if a >= modelo.anio - 2]
    anios = st.sidebar.multiselect(
        "Años en series de tráfico", anios_disponibles,
        default=por_defecto or anios_disponibles[:3],
        help="Aplica sólo a las series históricas de afluencia y aforo.",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"**{len(unidades)}** de {len(activas)} unidades seleccionadas · "
        f"corte {modelo.periodo_label}"
    )
    if st.sidebar.button("Recargar fuentes", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    return Seleccion(unidades=unidades, ciudades=ciudades, alcance=alcance,
                     anios_trafico=sorted(anios) or anios_disponibles[:3])
