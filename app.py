"""
Tablero Ejecutivo ARCO — punto de entrada.

Ejecución:
    streamlit run app.py

Este archivo sólo orquesta: pide datos al modelo, indicadores a la capa de
negocio y los entrega a los componentes. No contiene ninguna fórmula de KPI.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components import charts, filters, kpi_cards, layout, tables
from src import alerts, analytics, config, data_loader, insights, metrics
from src.data_model import build_model

layout.configurar_pagina()
layout.cargar_estilos()


@st.cache_data(show_spinner="Leyendo fuentes de ARCO…")
def cargar_modelo(firma: tuple):
    return build_model()


def firma_fuentes() -> tuple:
    """Huella de los archivos en data/raw: cambia cuando ARCO reemplaza una fuente."""
    partes = []
    for tipo in ("financiero", "afluencia", "cartera", "ocupacion"):
        p = data_loader.resolve_source(tipo)
        partes.append((tipo, p.name, p.stat().st_mtime) if p else (tipo, None, 0))
    return tuple(partes)


try:
    modelo = cargar_modelo(firma_fuentes())
except data_loader.FuenteNoEncontrada as exc:
    st.error(str(exc))
    st.info(
        "Coloque los archivos en `data/raw/`. Se reconocen por patrón, así que el "
        "mes puede seguir formando parte del nombre "
        "(por ejemplo `RF_Comparativos_por_Plaza_JULIO_2026.xlsx`)."
    )
    st.stop()

seleccion = filters.barra_lateral(modelo)
UNI = seleccion.unidades
ALC = seleccion.alcance
ACUM = ALC == "acum"
PERIODO = modelo.periodo_label if not ACUM else modelo.acumulado_label

kpis_mes = metrics.kpis_portafolio(modelo, "mes", UNI)
kpis_acum = metrics.kpis_portafolio(modelo, "acum", UNI)
kpis = kpis_mes if not ACUM else kpis_acum

layout.encabezado(modelo, kpis_mes, kpis_acum, ALC)

(tab_resumen, tab_fin, tab_op, tab_ocup, tab_car,
 tab_plaza, tab_datos) = st.tabs([
    "Resumen ejecutivo", "Financiero", "Operación", "Ocupación y GLA",
    "Cartera", "Detalle por plaza", "Datos y supuestos",
])


# ============================================================ RESUMEN ====
with tab_resumen:
    layout.titulo_seccion(f"Pulso del portafolio · {PERIODO}")
    comparativo = st.radio(
        "Comparar contra", ["Año anterior", "Presupuesto"],
        horizontal=True, label_visibility="collapsed", key="cmp_resumen",
    )
    modo = "ly" if comparativo == "Año anterior" else "ppto"
    kpi_cards.rejilla_kpis(kpi_cards.tarjetas_financieras(kpis, modo), 4)

    afl = metrics.trafico_comparativo(modelo, "afluencia", UNI, ACUM)
    afo = metrics.trafico_comparativo(modelo, "aforo", UNI, ACUM)
    car = metrics.cartera_resumen(modelo, UNI)
    dc_portafolio = metrics.dias_cartera(
        car["saldo"].sum(), car["facturacion_acum"].sum(), modelo.mes) if not car.empty else None

    operativas = []
    if not afl.empty:
        var = metrics.calculate_yoy(afl["actual"].sum(), afl["anterior"].sum())
        operativas.append(kpi_cards.create_kpi_card(
            "Afluencia peatonal", metrics.format_number(afl["actual"].sum()),
            f"Año anterior: {metrics.format_number(afl['anterior'].sum())}",
            var, metrics.format_variation(var)))
    if not afo.empty:
        var = metrics.calculate_yoy(afo["actual"].sum(), afo["anterior"].sum())
        operativas.append(kpi_cards.create_kpi_card(
            "Aforo vehicular", metrics.format_number(afo["actual"].sum()),
            f"Año anterior: {metrics.format_number(afo['anterior'].sum())}",
            var, metrics.format_variation(var)))
    if not car.empty:
        var_car = metrics.calculate_variance(car["saldo"].sum(), car["saldo_prev"].sum())["pct"]
        operativas.append(kpi_cards.create_kpi_card(
            "Cartera total", metrics.format_millions(car["saldo"].sum()),
            f"Mes anterior: {metrics.format_millions(car['saldo_prev'].sum())}",
            var_car, metrics.format_variation(var_car), invertir=True))
        operativas.append(kpi_cards.create_kpi_card(
            "Días cartera", f"{dc_portafolio:,.1f}" if dc_portafolio else "N/D",
            f"Objetivo: {config.UMBRALES['dc_objetivo']:.0f} días",
            (config.UMBRALES["dc_objetivo"] - (dc_portafolio or 0)),
            "Sobre objetivo" if (dc_portafolio or 0) > config.UMBRALES["dc_objetivo"]
            else "Dentro de objetivo"))
    ocup = metrics.ocupacion_portafolio(modelo, UNI)
    if ocup["ocupacion_pct"] is not None:
        operativas.append(kpi_cards.create_kpi_card(
            "Ocupación de GLA", metrics.format_percentage(ocup["ocupacion_pct"]),
            f"{metrics.format_number(ocup['gla_ocupada'])} de "
            f"{metrics.format_number(ocup['gla_total'])} m² arrendados",
            ocup["ocupacion_pct"] - config.UMBRALES["ocupacion_objetivo"],
            f"Objetivo {metrics.format_percentage(config.UMBRALES['ocupacion_objetivo'])}"))
        operativas.append(kpi_cards.create_kpi_card(
            "Renta en riesgo", metrics.format_millions(ocup["renta_en_riesgo"]),
            f"{metrics.format_number(ocup['gla_vacante'])} m² disponibles",
            -1, "Estimación mensual", invertir=True))
    if operativas:
        kpi_cards.rejilla_kpis(operativas, 4)

    layout.titulo_seccion("Hallazgos relevantes")
    kpi_cards.bloque_hallazgos(insights.generate_insights(modelo, UNI, ALC))

    layout.titulo_seccion("Alertas priorizadas")
    tabla_alertas = alerts.build_alerts(modelo, UNI, ALC, limite=40)
    conteo = alerts.conteo_por_severidad(tabla_alertas)
    cols = st.columns(4)
    for col, sev in zip(cols, config.SEVERIDADES):
        col.markdown(kpi_cards.create_kpi_card(
            config.SEVERIDAD_LABEL[sev], str(conteo[sev])), unsafe_allow_html=True)
    st.write("")
    kpi_cards.bloque_alertas(tabla_alertas, maximo=8)
    if len(tabla_alertas) > 8:
        with st.expander(f"Ver las {len(tabla_alertas) - 8} alertas restantes"):
            kpi_cards.bloque_alertas(tabla_alertas.iloc[8:], maximo=40)
    if not tabla_alertas.empty:
        tables.descargar_csv(
            tabla_alertas.drop(columns=["impacto"]),
            f"alertas_arco_{modelo.anio}{modelo.mes:02d}.csv",
            "Descargar alertas", key="dl_alertas")

    layout.titulo_seccion("Comparativo por plaza")
    maestra = tables.resumen_por_plaza(modelo, UNI, ALC)
    tables.tabla_comparativa(
        maestra,
        columnas_moneda=["Ingresos", "Ingresos AA", "Ingresos ppto", "Gastos",
                         "Gastos ppto", "UAIIDA", "Cartera", "Renta en riesgo"],
        columnas_pct=["% vs AA", "% vs ppto", "% UAIIDA vs AA", "Margen %",
                      "% Afl vs AA", "% Aforo vs AA", "% Ocupación"],
        columnas_entero=["Afluencia", "Aforo", "Días cartera", "GLA m²",
                         "m² disponibles", "Ingreso/m²"],
        altura=420)
    tables.descargar_csv(maestra, f"resumen_plazas_{modelo.anio}{modelo.mes:02d}.csv",
                         key="dl_maestra")
    if modelo.ocupacion.empty:
        layout.nota(
            "La columna <b>% Ocupación</b> aparece vacía porque no se detectó el archivo "
            "de ocupación en <code>data/raw/</code>. Vea la pestaña "
            "<i>Datos y supuestos</i> para activarla.")


# ========================================================== FINANCIERO ====
with tab_fin:
    layout.titulo_seccion(f"Real, presupuesto y año anterior · {PERIODO}")
    col_a, col_b = st.columns([1.1, 1])
    with col_a:
        st.markdown("**Ingresos, gastos y UAIIDA — Real vs presupuesto vs año anterior**")
        st.plotly_chart(charts.comparativo_financiero(kpis, PERIODO),
                        width="stretch", key="ch_fin_comparativo")
    with col_b:
        st.markdown("**Cumplimiento del portafolio**")
        filas = []
        for clave, etiqueta in (("ingresos", "Ingresos netos"),
                                ("gastos", "Gastos de operación"),
                                ("uaiida", "UAIIDA ajustado")):
            k = kpis[clave]
            filas.append({
                "Concepto": etiqueta,
                "Real": k["real"],
                "Presupuesto": k["ppto"],
                "Desviación": k["desv_ppto_abs"],
                "% vs ppto": (k["var_ppto"] * 100) if k["var_ppto"] is not None else None,
                "% vs año anterior": (k["var_ly"] * 100) if k["var_ly"] is not None else None,
            })
        tables.tabla_comparativa(pd.DataFrame(filas),
                                 ["Real", "Presupuesto", "Desviación"],
                                 ["% vs ppto", "% vs año anterior"])

    layout.titulo_seccion("Contribución a la desviación")
    concepto = st.selectbox(
        "Indicador a descomponer",
        ["Gastos de Operación", "Total Ingresos Netos", "UAIIDA Ajustado"],
        key="sel_desv")
    referencia = st.radio("Referencia", ["Presupuesto", "Año anterior"],
                          horizontal=True, key="ref_desv")
    col_ref = "ppto" if referencia == "Presupuesto" else "ly"

    base = metrics.pl_por_unidad(modelo, concepto, ALC, UNI)
    contrib = analytics.contribucion_desviacion(base, "real", col_ref, top=6)
    total_desv = base["real"].sum() - base[col_ref].sum()

    c1, c2 = st.columns([1, 1.15])
    with c1:
        st.markdown(
            f"**{concepto} — desviación total: "
            f"{metrics.format_millions(total_desv)} vs {referencia.lower()}**")
        st.plotly_chart(charts.contribucion_desviacion(contrib),
                        width="stretch", key="ch_contribucion")
    with c2:
        st.markdown("**Detalle de la aportación de cada plaza**")
        detalle = tables.tabla_desviaciones(contrib.rename(columns={col_ref: col_ref}))
        tables.tabla_comparativa(detalle, ["Real", "Referencia", "Desviación"],
                                 ["% Desviación", "% de la desviación total"])
        tables.descargar_csv(detalle, "contribucion_desviacion.csv", key="dl_desv")

    layout.titulo_seccion("Desviación por rubro")
    col_i, col_g = st.columns(2)
    with col_i:
        st.markdown(f"**Ingresos por rubro — desviación vs {referencia.lower()}**")
        rub_i = metrics.pl_rubros(modelo, "ingreso", ALC, UNI)
        if rub_i.empty:
            st.info("Sin rubros de ingreso con movimiento en la selección.")
        else:
            st.plotly_chart(
                charts.rubros_variacion(rub_i, col_ref, "MXN millones"),
                width="stretch", key="ch_rubros_ingreso")
    with col_g:
        st.markdown(f"**Gastos por rubro — desviación vs {referencia.lower()}**")
        rub_g = metrics.pl_rubros(modelo, "gasto", ALC, UNI)
        if rub_g.empty:
            st.info("Sin rubros de gasto con movimiento en la selección.")
        else:
            st.plotly_chart(
                charts.rubros_variacion(rub_g, col_ref, "MXN millones"),
                width="stretch", key="ch_rubros_gasto")

    with st.expander("Ver tabla de rubros"):
        for etiqueta, datos in (("Ingresos netos", rub_i), ("Gastos de operación", rub_g)):
            if datos.empty:
                continue
            st.markdown(f"**{etiqueta}**")
            vista = datos.reset_index().rename(columns={
                "concepto": "Rubro", "real": "Real",
                "ppto": "Presupuesto", "ly": "Año anterior"})
            vista["Desv. vs ppto"] = vista["Real"] - vista["Presupuesto"]
            vista["% vs AA"] = (vista["Real"] / vista["Año anterior"].replace(0, pd.NA) - 1) * 100
            tables.tabla_comparativa(
                vista, ["Real", "Presupuesto", "Año anterior", "Desv. vs ppto"], ["% vs AA"])
            tables.descargar_csv(vista, f"rubros_{etiqueta.lower().replace(' ', '_')}.csv",
                                 key=f"dl_rub_{etiqueta}")

    layout.titulo_seccion("Benchmark interno")
    bench = metrics.pl_por_unidad(modelo, "UAIIDA Ajustado", ALC, UNI).copy()
    ing_bench = metrics.pl_por_unidad(modelo, "Total Ingresos Netos", ALC, UNI)
    bench["margen"] = (bench["real"] / ing_bench["real"].replace(0, pd.NA)) * 100
    bench = analytics.benchmark_interno(bench, "margen")
    if not bench.empty:
        promedio = bench["margen"].mean()
        layout.nota(
            f"Margen UAIIDA promedio de las plazas seleccionadas: "
            f"<b>{promedio:,.1f} %</b>. Las plazas por debajo de esta línea tienen un "
            "problema propio, no del portafolio.")
        vista = bench.reset_index()[["plaza", "margen", "vs_promedio", "percentil"]]
        vista.columns = ["Plaza", "Margen %", "Puntos vs promedio", "Percentil"]
        vista["Percentil"] = vista["Percentil"] * 100
        tables.tabla_comparativa(vista, [], ["Margen %", "Puntos vs promedio", "Percentil"])


# =========================================================== OPERACIÓN ====
with tab_op:
    layout.titulo_seccion(f"Afluencia y aforo · {PERIODO}")
    for tipo, etiqueta, unidad_txt in (("afluencia", "Afluencia peatonal", "visitas"),
                                       ("aforo", "Aforo vehicular", "vehículos")):
        comp = metrics.trafico_comparativo(modelo, tipo, UNI, ACUM)
        if comp.empty:
            st.info(f"No hay datos de {etiqueta.lower()} para la selección vigente.")
            continue

        total_var = metrics.calculate_yoy(comp["actual"].sum(), comp["anterior"].sum())
        st.markdown(
            f"**{etiqueta} — {metrics.format_number(comp['actual'].sum())} {unidad_txt}, "
            f"{metrics.format_variation(total_var)} vs año anterior**")

        c1, c2 = st.columns([1.2, 1])
        with c1:
            serie = metrics.serie_trafico_mensual(modelo, tipo, seleccion.anios_trafico, UNI)
            if not serie.empty:
                st.plotly_chart(
                    charts.serie_mensual(serie, etiqueta, unidad_txt.capitalize()),
                    width="stretch", key=f"ch_serie_{tipo}")
        with c2:
            vista = comp.reset_index()[["plaza", "actual", "anterior", "var_pct"]]
            vista.columns = ["Plaza", f"{modelo.anio}", f"{modelo.anio - 1}", "% vs AA"]
            vista["% vs AA"] = vista["% vs AA"] * 100
            tables.tabla_comparativa(
                vista, [], ["% vs AA"], columnas_entero=[f"{modelo.anio}", f"{modelo.anio - 1}"])

        tend = analytics.tendencia_por_unidad(modelo, tipo, UNI)
        persistentes = tend[(tend["meses_negativos"] == tend["meses_evaluados"])
                            & (tend["meses_evaluados"] >= 3)]
        if not persistentes.empty:
            layout.nota(
                f"<b>Deterioro sostenido:</b> "
                f"{', '.join(persistentes['plaza'])} llevan todos los meses evaluados "
                f"por debajo del año anterior en {etiqueta.lower()}.")
        st.write("")

    layout.titulo_seccion("Indicadores normalizados por visita")
    layout.nota(
        "Normalizar por visita permite comparar plazas de tamaños distintos. "
        "Sólo se calcula cuando existe un denominador válido; las plazas sin "
        "afluencia reportada quedan fuera.")
    ratios = metrics.ratios_normalizados(modelo, UNI, ACUM)
    validos = ratios.dropna(subset=["ingreso_por_visita"])
    if validos.empty:
        st.info("Ninguna plaza seleccionada reporta afluencia peatonal.")
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("**Ingreso neto por visita — comparativo entre plazas**")
            st.plotly_chart(
                charts.barras_por_plaza(validos.reset_index(), "ingreso_por_visita",
                                        "MXN por visita", en_millones=False,
                                        formato="$%{y:,.2f}"),
                width="stretch", key="ch_ingreso_visita")
        with c2:
            st.markdown("**Ingreso por visita vs gasto por visita**")
            st.plotly_chart(
                charts.dispersion_benchmark(
                    validos.reset_index(), "gasto_por_visita", "ingreso_por_visita",
                    "plaza", "Gasto por visita (MXN)", "Ingreso por visita (MXN)"),
                width="stretch", key="ch_dispersion")

        vista = validos.reset_index()[["plaza", "afluencia", "aforo",
                                       "ingreso_por_visita", "gasto_por_visita",
                                       "ingreso_por_vehiculo"]]
        vista.columns = ["Plaza", "Afluencia", "Aforo", "Ingreso/visita",
                         "Gasto/visita", "Ingreso/vehículo"]
        tables.tabla_comparativa(vista, [], [], columnas_entero=["Afluencia", "Aforo"])
        tables.descargar_csv(vista, "indicadores_normalizados.csv", key="dl_ratios")


# ======================================================= OCUPACIÓN Y GLA ====
with tab_ocup:
    ocup_df = metrics.indicadores_por_m2(modelo, UNI, ACUM)
    port_ocup = metrics.ocupacion_portafolio(modelo, UNI)

    if ocup_df.empty:
        st.warning(
            "No se detectó el archivo de ocupación en `data/raw/`. "
            "Sin él no pueden calcularse la ocupación de GLA ni los indicadores por m². "
            "Consulte la pestaña *Datos y supuestos*.")
    else:
        layout.titulo_seccion(f"Ocupación de área rentable · {PERIODO}")
        kpi_cards.rejilla_kpis([
            kpi_cards.create_kpi_card(
                "Ocupación del portafolio",
                metrics.format_percentage(port_ocup["ocupacion_pct"]),
                f"Objetivo: {metrics.format_percentage(config.UMBRALES['ocupacion_objetivo'])}",
                port_ocup["ocupacion_pct"] - config.UMBRALES["ocupacion_objetivo"],
                f"{(port_ocup['ocupacion_pct'] - config.UMBRALES['ocupacion_objetivo']) * 100:+.1f} pp"),
            kpi_cards.create_kpi_card(
                "GLA total", f"{metrics.format_number(port_ocup['gla_total'])} m²",
                f"{port_ocup['plazas']} plazas con ocupación reportada"),
            kpi_cards.create_kpi_card(
                "Superficie disponible",
                f"{metrics.format_number(port_ocup['gla_vacante'])} m²",
                f"{metrics.format_percentage(1 - port_ocup['ocupacion_pct'])} del GLA"),
            kpi_cards.create_kpi_card(
                "Renta en riesgo",
                metrics.format_millions(port_ocup["renta_en_riesgo"]),
                "Renta mínima mensual estimada sobre los m² disponibles",
                -1, "Estimación", invertir=True),
        ], 4)
        layout.nota(
            "La ocupación del portafolio se pondera por GLA: "
            f"{metrics.format_number(port_ocup['gla_ocupada'])} m² arrendados sobre "
            f"{metrics.format_number(port_ocup['gla_total'])} m² rentables. "
            "Promediar los porcentajes de las plazas daría un número distinto y "
            "engañoso, porque trataría igual a una plaza de 7 mil m² y a una de 79 mil.")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Ocupación por plaza — contra el objetivo institucional**")
            st.plotly_chart(
                charts.barras_con_objetivo(
                    ocup_df.reset_index(), "ocupacion_pct",
                    config.UMBRALES["ocupacion_objetivo"], "% de GLA arrendado",
                    f"Objetivo {config.UMBRALES['ocupacion_objetivo']:.0%}"),
                width="stretch", key="ch_ocupacion")
        with c2:
            st.markdown("**Dónde cuesta el espacio vacío — renta mensual no colocada**")
            riesgo = ocup_df.reset_index()[["plaza", "renta_en_riesgo"]].dropna()
            st.plotly_chart(
                charts.barras_por_plaza(riesgo, "renta_en_riesgo", "MXN millones"),
                width="stretch", key="ch_renta_riesgo")

        peor_pct = ocup_df.nsmallest(1, "ocupacion_pct").iloc[0]
        peor_riesgo = ocup_df.nlargest(1, "renta_en_riesgo").iloc[0]
        if peor_pct["plaza"] != peor_riesgo["plaza"]:
            layout.nota(
                f"La ocupación más baja está en <b>{peor_pct['plaza']}</b> "
                f"({metrics.format_percentage(peor_pct['ocupacion_pct'])}), pero la "
                f"mayor renta no colocada está en <b>{peor_riesgo['plaza']}</b> "
                f"({metrics.format_millions(peor_riesgo['renta_en_riesgo'])} mensuales). "
                "El porcentaje señala la plaza más vacía; el importe señala dónde "
                "conviene concentrar la comercialización.")

        layout.titulo_seccion("Rendimiento por metro cuadrado")
        layout.nota(
            "Estar lleno no es lo mismo que rendir. Estos indicadores dividen entre "
            "los m² efectivamente arrendados, de modo que plazas de tamaños muy "
            "distintos se pueden comparar en igualdad de condiciones.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**UAIIDA por m² arrendado — comparativo entre plazas**")
            st.plotly_chart(
                charts.barras_por_plaza(ocup_df.reset_index(), "uaiida_por_m2",
                                        "MXN por m²", en_millones=False,
                                        formato="$%{y:,.0f} / m²"),
                width="stretch", key="ch_uaiida_m2")
        with c2:
            st.markdown("**Ocupación frente a rendimiento por m²**")
            disp = ocup_df.reset_index().copy()
            disp["ocupacion_pct"] = disp["ocupacion_pct"] * 100
            st.plotly_chart(
                charts.dispersion_benchmark(
                    disp, "ocupacion_pct", "uaiida_por_m2", "plaza",
                    "Ocupación (%)", "UAIIDA por m² (MXN)"),
                width="stretch", key="ch_ocup_vs_rend")

        layout.titulo_seccion("Detalle de superficie por plaza")
        vista = ocup_df.reset_index()[[
            "plaza", "ciudad", "gla_total", "gla_vacante", "ocupacion_pct",
            "ingreso_por_m2", "gasto_por_m2", "uaiida_por_m2", "renta_en_riesgo"]]
        vista.columns = ["Plaza", "Ciudad", "GLA m²", "m² disponibles", "% Ocupación",
                         "Ingreso/m²", "Gasto/m²", "UAIIDA/m²", "Renta en riesgo"]
        vista["% Ocupación"] = vista["% Ocupación"] * 100
        tables.tabla_comparativa(
            vista, ["Renta en riesgo"], ["% Ocupación"],
            columnas_entero=["GLA m²", "m² disponibles", "Ingreso/m²",
                             "Gasto/m²", "UAIIDA/m²"])
        tables.descargar_csv(vista, f"ocupacion_gla_{modelo.anio}{modelo.mes:02d}.csv",
                             key="dl_ocup")


# ============================================================== CARTERA ====
with tab_car:
    car = metrics.cartera_resumen(modelo, UNI)
    layout.titulo_seccion(f"Cartera · {modelo.periodo_label}")
    if car.empty:
        st.info("Sin datos de cartera para la selección vigente.")
    else:
        saldo, prev = car["saldo"].sum(), car["saldo_prev"].sum()
        var = metrics.calculate_variance(saldo, prev)["pct"]
        dc = metrics.dias_cartera(saldo, car["facturacion_acum"].sum(), modelo.mes)
        kpi_cards.rejilla_kpis([
            kpi_cards.create_kpi_card("Cartera total", metrics.format_millions(saldo),
                                      f"Mes anterior: {metrics.format_millions(prev)}",
                                      var, metrics.format_variation(var), invertir=True),
            kpi_cards.create_kpi_card("Días cartera", f"{dc:,.1f}" if dc else "N/D",
                                      f"Objetivo: {config.UMBRALES['dc_objetivo']:.0f} días"),
            kpi_cards.create_kpi_card(
                "Facturación acumulada",
                metrics.format_millions(car["facturacion_acum"].sum()),
                f"Enero–{config.MESES_ES[modelo.mes - 1]} {modelo.anio}"),
            kpi_cards.create_kpi_card(
                "Plazas sobre objetivo",
                str(int((car["dias_cartera"] > config.UMBRALES["dc_objetivo"]).sum())),
                f"de {len(car)} seleccionadas"),
        ], 4)

        c1, c2 = st.columns([1.15, 1])
        with c1:
            st.markdown("**Evolución mensual del saldo de cartera del portafolio filtrado**")
            st.plotly_chart(charts.cascada_cartera(metrics.serie_cartera(modelo, UNI)),
                            width="stretch", key="ch_cartera_serie")
        with c2:
            st.markdown("**Días cartera por plaza — contra el objetivo institucional**")
            dc_plaza = car.reset_index()[["plaza", "dias_cartera"]].dropna()
            st.plotly_chart(
                charts.barras_por_plaza(dc_plaza, "dias_cartera", "Días",
                                        en_millones=False, formato="%{y:,.1f} días"),
                width="stretch", key="ch_dias_cartera")

        layout.titulo_seccion("Saldo y antigüedad por plaza")
        vista = car.reset_index()[["plaza", "ciudad", "saldo", "saldo_prev",
                                   "var_mes_pct", "dias_cartera", "facturacion_acum"]]
        vista.columns = ["Plaza", "Ciudad", "Saldo", "Saldo mes anterior",
                         "% vs mes anterior", "Días cartera", "Facturación acumulada"]
        vista["% vs mes anterior"] = vista["% vs mes anterior"] * 100
        tables.tabla_comparativa(vista, ["Saldo", "Saldo mes anterior",
                                         "Facturación acumulada"],
                                 ["% vs mes anterior"], columnas_entero=["Días cartera"])
        tables.descargar_csv(vista, "cartera_por_plaza.csv", key="dl_car")

        layout.titulo_seccion("Concentración de deudores")
        n = st.slider("Número de clientes a mostrar", 5, 25, 10, key="n_deudores")
        top = metrics.cartera_top_clientes(modelo, UNI, n)
        if top.empty:
            st.info("Sin detalle de clientes para la selección vigente.")
        else:
            peso = top["saldo"].sum() / saldo if saldo else 0
            layout.nota(
                f"Los {len(top)} mayores deudores concentran "
                f"<b>{metrics.format_percentage(peso)}</b> de la cartera filtrada "
                f"({metrics.format_millions(top['saldo'].sum())}).")
            vista_top = top.copy()
            vista_top["participacion"] = vista_top["participacion"] * 100
            vista_top.columns = ["Cliente", "Plaza", "Saldo", "% de la cartera"]
            tables.tabla_comparativa(vista_top, ["Saldo"], ["% de la cartera"])
            tables.descargar_csv(vista_top, "top_deudores.csv", key="dl_top")

        layout.nota(
            "El archivo de cobranza reporta el saldo total por cliente y plaza, pero "
            "<b>no distingue cartera corriente de cartera en proceso legal</b>. "
            "Esa clasificación no está disponible en la fuente y conviene solicitarla "
            "a Jurídico y Cobranza.")


# ==================================================== DETALLE POR PLAZA ====
with tab_plaza:
    etiquetas = {u: config.UNIDADES[u]["nombre"] for u in UNI}
    elegida = st.selectbox("Plaza", list(etiquetas.values()), key="sel_plaza")
    unidad = next(u for u, n in etiquetas.items() if n == elegida)
    solo = [unidad]

    k_mes = metrics.kpis_portafolio(modelo, "mes", solo)
    k_acum = metrics.kpis_portafolio(modelo, "acum", solo)
    k_u = k_mes if not ACUM else k_acum

    var_i = k_u["ingresos"]["var_ly"]
    var_u = k_u["uaiida"]["var_ly"]
    estatus, tono = analytics.estatus_unidad(var_i, var_u)
    st.markdown(
        f"### {elegida} &nbsp; {layout.pill(estatus, tono)}"
        f"<div style='color:#53626d;font-size:14px;margin-top:2px;'>"
        f"{config.UNIDADES[unidad]['ciudad']} · {PERIODO}</div>",
        unsafe_allow_html=True)
    st.write("")

    kpi_cards.rejilla_kpis(kpi_cards.tarjetas_financieras(k_u, "ly"), 4)
    kpi_cards.rejilla_kpis(kpi_cards.tarjetas_financieras(k_u, "ppto"), 4)

    afl_u = metrics.trafico_comparativo(modelo, "afluencia", solo, ACUM)
    afo_u = metrics.trafico_comparativo(modelo, "aforo", solo, ACUM)
    car_u = metrics.cartera_resumen(modelo, solo)
    operativas = []
    if not afl_u.empty:
        v = afl_u["var_pct"].iloc[0]
        operativas.append(kpi_cards.create_kpi_card(
            "Afluencia", metrics.format_number(afl_u["actual"].iloc[0]),
            f"Año anterior: {metrics.format_number(afl_u['anterior'].iloc[0])}",
            v, metrics.format_variation(v)))
    if not afo_u.empty:
        v = afo_u["var_pct"].iloc[0]
        operativas.append(kpi_cards.create_kpi_card(
            "Aforo", metrics.format_number(afo_u["actual"].iloc[0]),
            f"Año anterior: {metrics.format_number(afo_u['anterior'].iloc[0])}",
            v, metrics.format_variation(v)))
    if not car_u.empty:
        operativas.append(kpi_cards.create_kpi_card(
            "Cartera", metrics.format_millions(car_u["saldo"].iloc[0]),
            f"Mes anterior: {metrics.format_millions(car_u['saldo_prev'].iloc[0])}",
            car_u["var_mes_pct"].iloc[0],
            metrics.format_variation(car_u["var_mes_pct"].iloc[0]), invertir=True))
        dcu = car_u["dias_cartera"].iloc[0]
        operativas.append(kpi_cards.create_kpi_card(
            "Días cartera", f"{dcu:,.1f}" if pd.notna(dcu) else "N/D",
            f"Objetivo: {config.UMBRALES['dc_objetivo']:.0f} días"))

    ocup_u = metrics.indicadores_por_m2(modelo, solo, ACUM)
    if not ocup_u.empty:
        fila_o = ocup_u.iloc[0]
        operativas.append(kpi_cards.create_kpi_card(
            "Ocupación", metrics.format_percentage(fila_o["ocupacion_pct"]),
            f"{metrics.format_number(fila_o['gla_total'])} m² de GLA · "
            f"{metrics.format_number(fila_o['gla_vacante'])} m² disponibles",
            fila_o["ocupacion_pct"] - config.UMBRALES["ocupacion_objetivo"],
            f"Objetivo {metrics.format_percentage(config.UMBRALES['ocupacion_objetivo'])}"))
        operativas.append(kpi_cards.create_kpi_card(
            "UAIIDA por m²", f"${fila_o['uaiida_por_m2']:,.0f}",
            f"Ingreso/m²: ${fila_o['ingreso_por_m2']:,.0f} · "
            f"Gasto/m²: ${fila_o['gasto_por_m2']:,.0f}"))
    if operativas:
        kpi_cards.rejilla_kpis(operativas, 4)

    layout.titulo_seccion("Hallazgos de la plaza")
    kpi_cards.bloque_hallazgos(insights.generate_insights(modelo, solo, ALC, maximo=5))

    layout.titulo_seccion("Detalle por rubro")
    c1, c2 = st.columns(2)
    for col, categoria, etiqueta in ((c1, "ingreso", "Ingresos netos"),
                                     (c2, "gasto", "Gastos de operación")):
        with col:
            st.markdown(f"**{etiqueta} — {elegida}**")
            datos = metrics.pl_rubros(modelo, categoria, ALC, solo)
            if datos.empty:
                st.info("Sin movimiento en la selección.")
                continue
            vista = datos.reset_index().rename(columns={
                "concepto": "Rubro", "real": "Real", "ppto": "Presupuesto",
                "ly": "Año anterior"})
            vista["% vs AA"] = (vista["Real"] / vista["Año anterior"].replace(0, pd.NA) - 1) * 100
            vista["% vs ppto"] = (vista["Real"] / vista["Presupuesto"].replace(0, pd.NA) - 1) * 100
            tables.tabla_comparativa(vista, ["Real", "Presupuesto", "Año anterior"],
                                     ["% vs AA", "% vs ppto"])

    if not modelo.trafico[modelo.trafico["unidad"] == unidad].empty:
        layout.titulo_seccion("Series históricas de tráfico")
        c1, c2 = st.columns(2)
        for col, tipo, etiqueta, unidad_txt in (
            (c1, "afluencia", "Afluencia peatonal", "Visitas"),
            (c2, "aforo", "Aforo vehicular", "Vehículos"),
        ):
            with col:
                serie = metrics.serie_trafico_mensual(modelo, tipo,
                                                      seleccion.anios_trafico, solo)
                if serie.empty:
                    st.info(f"{etiqueta} no se reporta para esta plaza.")
                    continue
                st.markdown(f"**{etiqueta} mensual — {elegida}**")
                st.plotly_chart(charts.serie_mensual(serie, etiqueta, unidad_txt),
                                width="stretch", key=f"ch_plaza_{tipo}")

    layout.titulo_seccion("Mayores deudores de la plaza")
    top_u = metrics.cartera_top_clientes(modelo, solo, 10)
    if top_u.empty:
        st.info("Sin detalle de clientes para esta plaza.")
    else:
        vista_top = top_u.copy()
        vista_top["participacion"] = vista_top["participacion"] * 100
        vista_top.columns = ["Cliente", "Plaza", "Saldo", "% de la cartera de la plaza"]
        tables.tabla_comparativa(vista_top, ["Saldo"], ["% de la cartera de la plaza"])


# ==================================================== DATOS Y SUPUESTOS ====
with tab_datos:
    layout.titulo_seccion("Ambiente")
    c1, c2 = st.columns([1, 2])
    c1.markdown(kpi_cards.create_kpi_card(
        "Ambiente", config.ENTORNO or "Sin etiquetar",
        "Definido por la variable ARCO_ENTORNO"), unsafe_allow_html=True)
    c2.markdown(kpi_cards.create_kpi_card(
        "Carpeta de datos", str(config.DATA_RAW),
        "Definida por la variable ARCO_DATA_DIR"), unsafe_allow_html=True)
    if not config.entorno_es_oficial():
        layout.nota(
            f"Este es el ambiente <b>{config.ENTORNO}</b>. Sus cifras pueden no "
            "coincidir con las del ambiente oficial si las fuentes se actualizaron "
            "en momentos distintos. Antes de citar un número, confirme el mes que "
            "aparece en <i>Última actualización de datos</i>.")

    layout.titulo_seccion("Fuentes detectadas")
    st.dataframe(data_loader.source_inventory(), width="stretch", hide_index=True)
    st.caption(
        "Los archivos se resuelven por patrón y se leen en modo lectura; nunca se "
        "modifican. Para actualizar el tablero basta con reemplazarlos en `data/raw/` "
        "y pulsar **Recargar fuentes** en la barra lateral."
    )

    layout.titulo_seccion("Periodo y cobertura")
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi_cards.create_kpi_card(
        "Última actualización de datos", modelo.periodo_label,
        "Determinada por el periodo máximo del libro financiero"), unsafe_allow_html=True)
    c2.markdown(kpi_cards.create_kpi_card(
        "Unidades con datos", str(len(modelo.unidades_activas)),
        f"de {len(config.ORDEN_UNIDADES)} en el catálogo"), unsafe_allow_html=True)
    c3.markdown(kpi_cards.create_kpi_card(
        "Años de historia de tráfico",
        f"{int(modelo.trafico['anio'].min())}–{int(modelo.trafico['anio'].max())}",
        "Afluencia y aforo mensual"), unsafe_allow_html=True)

    layout.titulo_seccion("Supuestos y limitaciones")
    for s in modelo.supuestos:
        st.markdown(f"- {s}")

    layout.titulo_seccion("Ocupación y GLA")
    if modelo.ocupacion.empty:
        st.markdown(
            "No se detectó el archivo de ocupación. Coloque en `data/raw/` un archivo "
            "cuyo nombre empiece con `OCUP` y que contenga, en una misma hoja, una "
            "columna encabezada **PLAZA** con la clave de la unidad, una columna "
            "**GLA** con el área rentable total y una columna **%** con la ocupación. "
            "El tablero localiza los encabezados por nombre, no por posición."
        )
    else:
        st.markdown(
            "El archivo de ocupación se lee localizando los encabezados **PLAZA**, "
            "**GLA** y **%**. Las columnas de superficie arrendada y disponible vienen "
            "sin título en el origen, así que se identifican verificando cuál "
            "reconstruye el porcentaje reportado; si no cuadraran, se derivan del GLA "
            "y el porcentaje. El mes puede seguir formando parte del nombre del "
            "archivo (`OCUP_JUN26.xlsx`)."
        )
        st.dataframe(modelo.ocupacion, width="stretch", hide_index=True)

    layout.titulo_seccion("Modelo normalizado")
    st.caption(
        "Estas tablas son la interfaz entre los datos y la aplicación. Migrar a SQL "
        "Server, SharePoint o Fabric implica reproducirlas; la interfaz no cambia."
    )
    conjuntos = {
        "Estado de resultados": modelo.pl,
        "Afluencia y aforo": modelo.trafico,
        "Cartera mensual": modelo.cartera_hist,
        "Cartera por cliente": modelo.cartera_clientes,
        "Facturación por rubro": modelo.facturacion_rubro,
        "Ocupación y GLA": modelo.ocupacion,
    }
    elegido = st.selectbox("Tabla", list(conjuntos.keys()), key="sel_modelo")
    datos = conjuntos[elegido]
    st.dataframe(datos.head(300), width="stretch", hide_index=True)
    st.caption(f"{len(datos):,} registros · mostrando los primeros 300.")
    tables.descargar_csv(datos, f"{elegido.lower().replace(' ', '_')}.csv",
                         "Descargar tabla completa", key="dl_modelo")
