"""Capa 3 — Tablas de investigación y descargas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config, metrics


def descargar_csv(df: pd.DataFrame, nombre: str, etiqueta: str = "Descargar CSV",
                  key: str | None = None) -> None:
    st.download_button(
        etiqueta,
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=nombre,
        mime="text/csv",
        key=key,
        use_container_width=False,
    )


def tabla_comparativa(df: pd.DataFrame, columnas_moneda: list[str],
                      columnas_pct: list[str] = (), altura: int | None = None,
                      columnas_entero: list[str] = ()) -> None:
    """
    Tabla con formato ejecutivo. Se muestran sólo columnas de negocio; los
    identificadores técnicos se omiten.
    """
    conf = {}
    for c in columnas_moneda:
        if c in df.columns:
            conf[c] = st.column_config.NumberColumn(c, format="$%,.0f")
    for c in columnas_pct:
        if c in df.columns:
            conf[c] = st.column_config.NumberColumn(c, format="%.1f %%")
    for c in columnas_entero:
        if c in df.columns:
            conf[c] = st.column_config.NumberColumn(c, format="%,.0f")

    extra = {"height": altura} if altura else {}
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config=conf, **extra)


def tabla_desviaciones(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara la tabla de contribución a la desviación para presentación."""
    out = pd.DataFrame({
        "Plaza": df["plaza"],
        "Real": df["real"],
        "Referencia": df[[c for c in ("ppto", "ly") if c in df.columns][0]],
        "Desviación": df["desviacion"],
        "% Desviación": df["desviacion_pct"] * 100,
        "% de la desviación total": df["contribucion_pct"] * 100,
    })
    return out


def resumen_por_plaza(modelo, unidades, alcance) -> pd.DataFrame:
    """
    Tabla maestra: una fila por plaza con lo financiero, lo operativo y la
    cartera. Es el punto de entrada para investigar cualquier desviación.
    """
    from src import analytics

    ing = metrics.pl_por_unidad(modelo, "Total Ingresos Netos", alcance, unidades)
    gas = metrics.pl_por_unidad(modelo, "Gastos de Operación", alcance, unidades)
    ua = metrics.pl_por_unidad(modelo, "UAIIDA Ajustado", alcance, unidades)
    acumulado = alcance == "acum"
    afl = metrics.trafico_comparativo(modelo, "afluencia", unidades, acumulado)
    afo = metrics.trafico_comparativo(modelo, "aforo", unidades, acumulado)
    car = metrics.cartera_resumen(modelo, unidades)
    ocupacion = metrics.ocupacion_resumen(modelo, unidades, alcance == "acum")
    ocu = (ocupacion["ocupacion_pct"] if not ocupacion.empty else pd.Series(dtype=float))
    gla = (ocupacion["gla_total"] if not ocupacion.empty else pd.Series(dtype=float))
    vac = (ocupacion["gla_vacante"] if not ocupacion.empty else pd.Series(dtype=float))
    riesgo = (ocupacion["renta_en_riesgo"] if not ocupacion.empty else pd.Series(dtype=float))

    filas = []
    for u in ing.index:
        var_i = metrics.calculate_yoy(ing.loc[u, "real"], ing.loc[u, "ly"])
        var_u = metrics.calculate_yoy(ua.loc[u, "real"], ua.loc[u, "ly"])
        estatus, _ = analytics.estatus_unidad(var_i, var_u)
        margen = ua.loc[u, "real"] / ing.loc[u, "real"] if ing.loc[u, "real"] else None
        filas.append({
            "Plaza": ing.loc[u, "plaza"],
            "Ciudad": ing.loc[u, "ciudad"],
            "Estatus": estatus,
            "Ingresos": ing.loc[u, "real"],
            "Ingresos AA": ing.loc[u, "ly"],
            "% vs AA": (var_i * 100) if var_i is not None else None,
            "Ingresos ppto": ing.loc[u, "ppto"],
            "% vs ppto": ((ing.loc[u, "real"] / ing.loc[u, "ppto"] - 1) * 100
                          if ing.loc[u, "ppto"] else None),
            "Gastos": gas.loc[u, "real"],
            "Gastos ppto": gas.loc[u, "ppto"],
            "UAIIDA": ua.loc[u, "real"],
            "% UAIIDA vs AA": (var_u * 100) if var_u is not None else None,
            "Margen %": (margen * 100) if margen is not None else None,
            "Afluencia": afl["actual"].get(u) if not afl.empty else None,
            "% Afl vs AA": (afl["var_pct"].get(u) * 100
                            if not afl.empty and pd.notna(afl["var_pct"].get(u)) else None),
            "Aforo": afo["actual"].get(u) if not afo.empty else None,
            "% Aforo vs AA": (afo["var_pct"].get(u) * 100
                              if not afo.empty and pd.notna(afo["var_pct"].get(u)) else None),
            "Cartera": car["saldo"].get(u) if not car.empty else None,
            "Días cartera": car["dias_cartera"].get(u) if not car.empty else None,
            "% Ocupación": (ocu.get(u) * 100) if len(ocu) and pd.notna(ocu.get(u)) else None,
            "GLA m²": gla.get(u) if len(gla) else None,
            "m² disponibles": vac.get(u) if len(vac) else None,
            "Renta en riesgo": riesgo.get(u) if len(riesgo) else None,
            "Ingreso/m²": (ing.loc[u, "real"] / ocupacion.loc[u, "gla_ocupada"]
                           if u in ocupacion.index and ocupacion.loc[u, "gla_ocupada"]
                           else None),
        })
    return pd.DataFrame(filas)
