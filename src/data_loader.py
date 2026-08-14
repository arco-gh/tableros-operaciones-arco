"""
Capa 1 — Lectura de las fuentes.

Este módulo es el único que conoce la estructura física de los archivos Excel.
El resto de la aplicación consume exclusivamente el modelo normalizado que
produce `data_model.py`. Sustituir Excel por SQL, Fabric o una API implica
reescribir sólo este archivo.

Los archivos originales se tratan como READ ONLY: se abren en modo lectura y
nunca se escriben.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from . import config

warnings.filterwarnings("ignore", message=".*Conditional Formatting.*")
warnings.filterwarnings("ignore", message=".*Unknown extension.*")

try:  # el módulo debe poder importarse fuera de Streamlit (tests, ETL)
    import streamlit as st

    cache = st.cache_data
except Exception:  # pragma: no cover
    def cache(*dargs, **dkwargs):
        def wrapper(fn):
            return fn
        if dargs and callable(dargs[0]):
            return dargs[0]
        return wrapper


class FuenteNoEncontrada(FileNotFoundError):
    """La carpeta data/raw no contiene un archivo que cumpla el patrón."""


def resolve_source(kind: str, data_dir: Path | None = None) -> Path | None:
    """
    Localiza el archivo más reciente que cumple el patrón declarado para `kind`.

    Se resuelve por patrón y no por nombre literal porque los archivos de ARCO
    incluyen el mes en el nombre (RF_Comparativos..._JUNIO_2026...).
    """
    data_dir = Path(data_dir or config.DATA_RAW)
    candidatos: list[Path] = []
    for pattern in config.FILE_PATTERNS.get(kind, []):
        candidatos.extend(p for p in data_dir.glob(pattern) if not p.name.startswith("~$"))
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def require_source(kind: str, data_dir: Path | None = None) -> Path:
    path = resolve_source(kind, data_dir)
    if path is None:
        patrones = ", ".join(config.FILE_PATTERNS.get(kind, []))
        raise FuenteNoEncontrada(
            f"No se encontró el archivo de '{kind}' en {config.DATA_RAW}. "
            f"Patrones esperados: {patrones}"
        )
    return path


def source_inventory(data_dir: Path | None = None) -> pd.DataFrame:
    """Inventario de las fuentes detectadas, para la pestaña de gobierno de datos."""
    filas = []
    for kind in config.FILE_PATTERNS:
        path = resolve_source(kind, data_dir)
        if path is None:
            filas.append({
                "Fuente": kind,
                "Archivo": "— no encontrado —",
                "Tamaño (KB)": None,
                "Modificado": None,
                "Hojas": None,
            })
            continue
        try:
            hojas = len(pd.ExcelFile(path).sheet_names)
        except Exception:
            hojas = None
        filas.append({
            "Fuente": kind,
            "Archivo": path.name,
            "Tamaño (KB)": round(path.stat().st_size / 1024, 1),
            "Modificado": pd.Timestamp(path.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"),
            "Hojas": hojas,
        })
    return pd.DataFrame(filas)


def _cache_key(path: Path) -> tuple[str, float, int]:
    """Firma del archivo: invalida el caché cuando ARCO reemplaza la fuente."""
    stat = path.stat()
    return (str(path), stat.st_mtime, stat.st_size)


@cache(show_spinner=False)
def _read_sheet(key: tuple[str, float, int], sheet: str) -> pd.DataFrame:
    return pd.read_excel(key[0], sheet_name=sheet, header=None, engine="openpyxl")


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    """Lee una hoja sin encabezado. El caché se invalida si el archivo cambia."""
    return _read_sheet(_cache_key(path), sheet)


def sheet_names(path: Path) -> list[str]:
    return pd.ExcelFile(path, engine="openpyxl").sheet_names
