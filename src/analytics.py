"""
Capa 2 — Analítica de diagnóstico.

Responde a la pregunta que un tablero de semáforos no responde: *qué unidad
explica cuánto de la desviación*, cómo se comporta la serie más allá de dos
puntos, y qué plazas se salen del patrón del portafolio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, metrics
from .data_model import ModeloARCO


def contribucion_desviacion(df: pd.DataFrame, col_real: str = "real",
                            col_ref: str = "ppto", top: int = 5) -> pd.DataFrame:
    """
    Descompone la desviación total del portafolio en la aportación de cada unidad.

    Ejemplo de lectura: si el gasto está $1.20 M sobre presupuesto, esta tabla
    dice que Paseo Villalta aporta $420 mil de esos $1.20 M (35 %).
    """
    if df.empty:
        return df
    out = df.copy()
    out["desviacion"] = out[col_real] - out[col_ref]
    total = out["desviacion"].sum()
    out["contribucion_pct"] = out["desviacion"] / total if total else np.nan
    out["desviacion_pct"] = out.apply(
        lambda r: metrics.calculate_variance(r[col_real], r[col_ref])["pct"], axis=1)
    out = out.reindex(out["desviacion"].abs().sort_values(ascending=False).index)

    if len(out) > top:
        cabeza = out.head(top).copy()
        cola = out.iloc[top:]
        otros = pd.DataFrame([{
            "plaza": f"Otras {len(cola)} unidades",
            "ciudad": "—",
            col_real: cola[col_real].sum(),
            col_ref: cola[col_ref].sum(),
            "desviacion": cola["desviacion"].sum(),
            "contribucion_pct": cola["desviacion"].sum() / total if total else np.nan,
            "desviacion_pct": np.nan,
        }], index=["OTROS"])
        out = pd.concat([cabeza, otros])
    return out


def tendencia_serie(valores: pd.Series) -> dict:
    """
    Caracteriza una serie temporal: pendiente relativa, periodos consecutivos de
    deterioro o de recuperación, y último cambio.
    """
    s = pd.Series(valores).dropna().astype(float)
    if len(s) < 2:
        return {"pendiente_pct": None, "deterioro_consecutivo": 0,
                "mejora_consecutiva": 0, "ultimo_cambio_pct": None, "n": len(s)}

    x = np.arange(len(s))
    pendiente = np.polyfit(x, s.values, 1)[0]
    base = s.mean()
    diffs = s.diff().dropna()

    def _racha(signo: int) -> int:
        n = 0
        for d in reversed(diffs.values):
            if (d < 0 and signo < 0) or (d > 0 and signo > 0):
                n += 1
            else:
                break
        return n

    return {
        "pendiente_pct": pendiente / base if base else None,
        "deterioro_consecutivo": _racha(-1),
        "mejora_consecutiva": _racha(1),
        "ultimo_cambio_pct": (s.iloc[-1] / s.iloc[-2] - 1) if s.iloc[-2] else None,
        "n": len(s),
    }


def benchmark_interno(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    """
    Sitúa cada unidad frente al portafolio: promedio, mediana y mejor unidad.

    Sirve para distinguir un problema general del portafolio de un problema
    puntual de una plaza.
    """
    if df.empty or columna not in df:
        return df
    serie = df[columna].dropna()
    if serie.empty:
        return df
    out = df.copy()
    out["vs_promedio"] = out[columna] - serie.mean()
    out["vs_mediana"] = out[columna] - serie.median()
    out["vs_mejor"] = out[columna] - serie.max()
    out["percentil"] = out[columna].rank(pct=True)
    return out


def detectar_outliers(serie: pd.Series, z: float = 2.0) -> pd.Series:
    """Marca valores que se alejan más de `z` desviaciones estándar de la media."""
    s = pd.Series(serie).dropna().astype(float)
    if len(s) < 4 or s.std(ddof=0) == 0:
        return pd.Series(False, index=pd.Series(serie).index)
    puntajes = (pd.Series(serie).astype(float) - s.mean()) / s.std(ddof=0)
    return puntajes.abs() > z


def tendencia_por_unidad(modelo: ModeloARCO, tipo: str = "afluencia",
                         unidades: list[str] | None = None,
                         meses: int = 6) -> pd.DataFrame:
    """
    Tendencia reciente de tráfico por unidad, comparando cada mes contra el
    mismo mes del año anterior (evita confundir estacionalidad con deterioro).
    """
    unidades = metrics.filtrar_unidades(modelo, unidades)
    t = modelo.trafico
    filas = []
    inicio = max(1, modelo.mes - meses + 1)
    for u in unidades:
        act = t[(t["tipo"] == tipo) & (t["unidad"] == u) & (t["anio"] == modelo.anio)
                & (t["mes"].between(inicio, modelo.mes))].set_index("mes")["valor"]
        ant = t[(t["tipo"] == tipo) & (t["unidad"] == u) & (t["anio"] == modelo.anio - 1)
                & (t["mes"].between(inicio, modelo.mes))].set_index("mes")["valor"]
        if act.empty or ant.empty:
            continue
        rel = (act / ant.reindex(act.index)).dropna() - 1
        info = tendencia_serie(rel)
        filas.append({
            "unidad": u,
            "plaza": config.UNIDADES[u]["nombre"],
            "var_promedio": rel.mean(),
            "meses_negativos": int((rel < 0).sum()),
            "meses_evaluados": int(len(rel)),
            "deterioro_consecutivo": info["deterioro_consecutivo"],
        })
    columnas = ["unidad", "plaza", "var_promedio", "meses_negativos",
                "meses_evaluados", "deterioro_consecutivo"]
    return pd.DataFrame(filas, columns=columnas)


def deterioro_cartera(modelo: ModeloARCO, unidades: list[str] | None = None) -> pd.DataFrame:
    """Unidades cuya cartera crece de forma sostenida en los últimos meses."""
    unidades = metrics.filtrar_unidades(modelo, unidades)
    h = modelo.cartera_hist
    filas = []
    for u in unidades:
        s = (h[h["unidad"] == u].sort_values(["anio", "mes"])["saldo"]
             .reset_index(drop=True))
        if len(s) < 3:
            continue
        info = tendencia_serie(s)
        filas.append({
            "unidad": u,
            "plaza": config.UNIDADES[u]["nombre"],
            "meses_al_alza": info["mejora_consecutiva"],
            "pendiente_pct": info["pendiente_pct"],
            "ultimo_cambio_pct": info["ultimo_cambio_pct"],
            "saldo_actual": s.iloc[-1],
        })
    columnas = ["unidad", "plaza", "meses_al_alza", "pendiente_pct",
                "ultimo_cambio_pct", "saldo_actual"]
    return pd.DataFrame(filas, columns=columnas)


def estatus_unidad(var_ingresos: float | None, var_uaiida: float | None) -> tuple[str, str]:
    """Semáforo ejecutivo por unidad, en función del crecimiento de ingresos y UAIIDA."""
    vi = var_ingresos if var_ingresos is not None else 0
    vu = var_uaiida if var_uaiida is not None else 0
    if vi < 0 and vu < 0:
        return "Crítico", "rojo"
    if vu < 0:
        return "Atención", "ambar"
    return "Saludable", "verde"
