"""
Conciliación del modelo contra el reporte oficial.

Ejecutar después de cada actualización mensual de archivos:

    python scripts/validar_fuentes.py

Compara los consolidados que produce la aplicación contra la hoja de resumen del
libro financiero (cuando existe) y reporta cualquier diferencia mayor a un peso.
Si la conciliación falla, el dato del tablero no debe presentarse al Comité hasta
entender la causa.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, data_loader as dl, metrics  # noqa: E402
from src.data_model import build_model  # noqa: E402

TOLERANCIA = 1.0


def hoja_resumen(path: Path) -> str | None:
    for hoja in dl.sheet_names(path):
        if hoja.upper().startswith("RESUMEN"):
            return hoja
    return None


def leer_suma_oficial(path: Path, hoja: str) -> dict:
    """Extrae las filas SUMA (mes y acumulado) de la hoja de resumen ejecutivo."""
    df = dl.read_sheet(path, hoja)
    resultado = {}
    encontrados = 0
    for i in range(df.shape[0]):
        if str(df.iloc[i, 1]).strip().upper() == "SUMA":
            alcance = "mes" if encontrados == 0 else "acum"
            resultado[alcance] = {
                "ingresos": float(df.iloc[i, 3]),
                "gastos": float(df.iloc[i, 7]),
                "uaiida": float(df.iloc[i, 11]),
            }
            encontrados += 1
            if encontrados == 2:
                break
    return resultado


def main() -> int:
    modelo = build_model()
    print(f"Periodo detectado: {modelo.periodo_label}")
    print(f"Unidades con datos: {', '.join(modelo.unidades_activas)}\n")

    path = modelo.fuentes["financiero"]
    hoja = hoja_resumen(path)
    if hoja is None:
        print("No se encontró hoja de resumen; se omite la conciliación financiera.")
        return 0
    print(f"Conciliando contra la hoja '{hoja}' de {path.name}\n")

    oficial = leer_suma_oficial(path, hoja)
    fallos = 0
    filas = []
    for alcance, valores in oficial.items():
        calculado = metrics.kpis_portafolio(modelo, alcance)
        for clave in ("ingresos", "gastos", "uaiida"):
            dif = calculado[clave]["real"] - valores[clave]
            ok = abs(dif) <= TOLERANCIA
            fallos += 0 if ok else 1
            filas.append({
                "Alcance": alcance,
                "Concepto": clave,
                "Modelo": round(calculado[clave]["real"], 2),
                "Excel": round(valores[clave], 2),
                "Diferencia": round(dif, 2),
                "Estado": "OK" if ok else "DIFIERE",
            })
    print(pd.DataFrame(filas).to_string(index=False))

    print("\nCartera por unidad:")
    car = metrics.cartera_resumen(modelo)
    print(car[["plaza", "saldo", "dias_cartera"]].round(2).to_string(index=False))
    print(f"\nCartera total: {metrics.format_currency(car['saldo'].sum(), 2)}")

    if modelo.ocupacion.empty:
        print("\nAviso: sin archivo de ocupación en data/raw (patrón OCUP*.xlsx).")
    else:
        ocup = metrics.ocupacion_resumen(modelo)
        port = metrics.ocupacion_portafolio(modelo)
        print("\nOcupación por unidad:")
        print(ocup[["plaza", "gla_total", "gla_vacante", "ocupacion_pct"]]
              .round(4).to_string(index=False))
        print(f"\nGLA total: {port['gla_total']:,.2f} m² · "
              f"Ocupación ponderada: {port['ocupacion_pct']:.4%} · "
              f"Renta en riesgo: {metrics.format_currency(port['renta_en_riesgo'], 2)}")
        # La suma de superficies debe reconstruir el GLA reportado.
        desfase = (ocup["gla_ocupada"] + ocup["gla_vacante"] - ocup["gla_total"]).abs().max()
        if desfase > TOLERANCIA:
            print(f"AVISO: arrendado + disponible no cuadra con el GLA "
                  f"(desfase máximo {desfase:,.2f} m²).")
            fallos += 1

    print("\nSupuestos vigentes:")
    for s in modelo.supuestos:
        print(f"  - {s}")

    if fallos:
        print(f"\n{fallos} concepto(s) no concilian. Revisar antes de publicar.")
        return 1
    print("\nConciliación correcta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
