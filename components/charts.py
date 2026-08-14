"""
Capa 3 — Gráficas.

Todas las figuras pasan por `apply_arco_layout`, de modo que tipografía,
márgenes, gridlines y formato numérico se definen en un solo lugar.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src import config, metrics

FUENTE = dict(family="Barlow, system-ui, sans-serif", size=12,
              color=config.PALETA["tinta"])


def apply_arco_layout(fig: go.Figure, titulo_y: str = "", altura: int = 320,
                      leyenda: bool = True, formato_y: str | None = None) -> go.Figure:
    """Aplica la identidad visual de ARCO a cualquier figura de Plotly."""
    fig.update_layout(
        font=FUENTE,
        height=altura,
        margin=dict(l=8, r=8, t=28, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(font=FUENTE, bgcolor="white", bordercolor=config.PALETA["linea"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=11.5)) if leyenda else dict(),
        showlegend=leyenda,
        colorway=config.SECUENCIA_COLORES,
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, linecolor=config.PALETA["linea"],
                     tickfont=dict(size=11.5))
    fig.update_yaxes(gridcolor="#eef1f4", zerolinecolor=config.PALETA["linea"],
                     title_text=titulo_y, title_font=dict(size=11),
                     tickfont=dict(size=11), tickformat=formato_y)
    return fig


def comparativo_financiero(kpis: dict, titulo_periodo: str) -> go.Figure:
    """Ingresos, gastos y UAIIDA: real contra presupuesto y contra año anterior."""
    categorias = ["Ingresos netos", "Gastos de operación", "UAIIDA ajustado"]
    claves = ["ingresos", "gastos", "uaiida"]
    series = [
        ("Año anterior", "ly", config.PALETA["gris"]),
        ("Presupuesto", "ppto", config.PALETA["azul_1"]),
        (f"Real {titulo_periodo}", "real", config.PALETA["azul_2"]),
    ]
    fig = go.Figure()
    for nombre, campo, color in series:
        valores = [kpis[c][campo] / 1e6 for c in claves]
        fig.add_bar(
            name=nombre, x=categorias, y=valores, marker_color=color,
            hovertemplate="%{x}<br>" + nombre + ": $%{y:,.2f} M<extra></extra>",
        )
    fig.update_layout(barmode="group")
    return apply_arco_layout(fig, "MXN millones", altura=340)


def contribucion_desviacion(df: pd.DataFrame, titulo_y: str = "MXN millones") -> go.Figure:
    """Barras horizontales: aportación de cada unidad a la desviación consolidada."""
    d = df.iloc[::-1]
    colores = [config.PALETA["rojo"] if v > 0 else config.PALETA["verde"]
               for v in d["desviacion"]]
    fig = go.Figure(go.Bar(
        x=d["desviacion"] / 1e6, y=d["plaza"], orientation="h",
        marker_color=colores,
        customdata=[[c] for c in d["contribucion_pct"].fillna(0)],
        hovertemplate="%{y}<br>Desviación: $%{x:,.2f} M"
                      "<br>Contribución: %{customdata[0]:.1%}<extra></extra>",
    ))
    fig.update_xaxes(title_text=titulo_y)
    return apply_arco_layout(fig, "", altura=max(240, 42 * len(d)), leyenda=False)


def serie_mensual(df: pd.DataFrame, nombre_valor: str, titulo_y: str,
                  altura: int = 330) -> go.Figure:
    """Serie mensual con una línea por año, para leer tendencia y estacionalidad."""
    fig = go.Figure()
    for i, anio in enumerate(df.columns):
        fig.add_scatter(
            x=[config.MESES_ABR[m - 1] for m in df.index],
            y=df[anio], mode="lines+markers", name=str(int(anio)),
            line=dict(width=3 if i == len(df.columns) - 1 else 2),
            hovertemplate=f"{nombre_valor} %{{x}} {int(anio)}: %{{y:,.0f}}<extra></extra>",
        )
    return apply_arco_layout(fig, titulo_y, altura=altura)


def barras_por_plaza(df: pd.DataFrame, columna: str, titulo_y: str,
                     en_millones: bool = True, formato: str = "$%{y:,.2f} M") -> go.Figure:
    """Ranking de plazas para un indicador, ordenado de mayor a menor."""
    d = df.sort_values(columna, ascending=False)
    valores = d[columna] / 1e6 if en_millones else d[columna]
    fig = go.Figure(go.Bar(
        x=d["plaza"], y=valores, marker_color=config.PALETA["azul_1"],
        hovertemplate="%{x}<br>" + formato + "<extra></extra>",
    ))
    fig.update_xaxes(tickangle=-25)
    return apply_arco_layout(fig, titulo_y, altura=330, leyenda=False)


def barras_comparadas(df: pd.DataFrame, col_a: str, col_b: str,
                      nombre_a: str, nombre_b: str, titulo_y: str,
                      divisor: float = 1e6, formato: str = "$%{y:,.2f} M") -> go.Figure:
    """Comparación lado a lado por plaza (real vs referencia)."""
    fig = go.Figure()
    fig.add_bar(name=nombre_b, x=df["plaza"], y=df[col_b] / divisor,
                marker_color=config.PALETA["gris"],
                hovertemplate="%{x}<br>" + nombre_b + ": " + formato + "<extra></extra>")
    fig.add_bar(name=nombre_a, x=df["plaza"], y=df[col_a] / divisor,
                marker_color=config.PALETA["azul_2"],
                hovertemplate="%{x}<br>" + nombre_a + ": " + formato + "<extra></extra>")
    fig.update_layout(barmode="group")
    fig.update_xaxes(tickangle=-25)
    return apply_arco_layout(fig, titulo_y, altura=340)


def cascada_cartera(serie: pd.DataFrame) -> go.Figure:
    """Evolución mensual del saldo de cartera del portafolio filtrado."""
    fig = go.Figure(go.Scatter(
        x=serie["periodo"], y=serie["saldo"] / 1e6, mode="lines+markers",
        line=dict(color=config.PALETA["azul_2"], width=3),
        fill="tozeroy", fillcolor="rgba(74,124,158,.12)",
        hovertemplate="%{x}: $%{y:,.2f} M<extra></extra>",
    ))
    return apply_arco_layout(fig, "MXN millones", altura=300, leyenda=False)


def dispersion_benchmark(df: pd.DataFrame, x: str, y: str, etiqueta: str,
                         titulo_x: str, titulo_y: str) -> go.Figure:
    """Posiciona cada plaza en dos dimensiones para separar tamaño de desempeño."""
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="markers+text", text=df[etiqueta],
        textposition="top center", textfont=dict(size=10),
        marker=dict(size=13, color=config.PALETA["azul_1"],
                    line=dict(width=1, color="white")),
        hovertemplate="%{text}<br>" + titulo_x + ": %{x:,.2f}<br>"
                      + titulo_y + ": %{y:,.2f}<extra></extra>",
    ))
    fig.update_xaxes(title_text=titulo_x)
    return apply_arco_layout(fig, titulo_y, altura=380, leyenda=False)


def barras_con_objetivo(df: pd.DataFrame, columna: str, objetivo: float,
                        titulo_y: str, etiqueta_objetivo: str,
                        formato: str = "%{y:.1%}") -> go.Figure:
    """
    Ranking por plaza contra una línea de objetivo institucional.

    El color separa a quien cumple de quien no, para que la lectura no dependa
    de comparar alturas de barra contra una línea.
    """
    d = df.sort_values(columna, ascending=False)
    colores = [config.PALETA["azul_1"] if v >= objetivo else config.PALETA["ambar"]
               for v in d[columna]]
    fig = go.Figure(go.Bar(
        x=d["plaza"], y=d[columna], marker_color=colores,
        hovertemplate="%{x}<br>" + formato + "<extra></extra>",
    ))
    fig.add_hline(y=objetivo, line_dash="dash", line_color=config.PALETA["azul_2"],
                  annotation_text=etiqueta_objetivo, annotation_position="top left",
                  annotation_font_size=11)
    fig.update_xaxes(tickangle=-25)
    return apply_arco_layout(fig, titulo_y, altura=340, leyenda=False,
                             formato_y=".0%" if objetivo <= 1 else None)


def rubros_variacion(df: pd.DataFrame, referencia: str, titulo: str) -> go.Figure:
    """Desviación por rubro contra la referencia elegida, ordenada por impacto."""
    d = df.copy()
    d["delta"] = d["real"] - d[referencia]
    d = d.reindex(d["delta"].abs().sort_values().index)
    colores = [config.PALETA["rojo"] if v > 0 else config.PALETA["verde"] for v in d["delta"]]
    fig = go.Figure(go.Bar(
        x=d["delta"] / 1e6, y=d.index, orientation="h", marker_color=colores,
        hovertemplate="%{y}<br>Desviación: $%{x:,.2f} M<extra></extra>",
    ))
    fig.update_xaxes(title_text=titulo)
    return apply_arco_layout(fig, "", altura=max(260, 30 * len(d)), leyenda=False)
