# Despliegue — Tablero Ejecutivo ARCO

## Guías

| Ambiente | Guía | Medio |
|---|---|---|
| Azure App Service | **[DEPLOY_AZURE_PORTAL.md](DEPLOY_AZURE_PORTAL.md)** | Portal web, sin línea de comandos |
| Azure App Service | **[DEPLOY_AZURE.md](DEPLOY_AZURE.md)** | Azure CLI |
| Windows Server con IIS | **[DEPLOY_WINDOWS_IIS.md](DEPLOY_WINDOWS_IIS.md)** | IIS Manager y PowerShell (trae apéndice de equivalencias gráficas) |
| Docker | Sección final de este documento | Línea de comandos |

Cada guía es autocontenida: se puede seguir sin haber leído las otras. Las dos
guías de Azure producen exactamente el mismo resultado; elija según con qué
medio esté más cómodo TI.

**Cuándo conviene cada medio.** El portal es mejor para el primer despliegue,
porque cada pantalla muestra las opciones disponibles y sus valores válidos. La
línea de comandos es mejor para reproducir el despliegue —levantar un ambiente
de prueba idéntico, o rehacerlo tras un incidente— porque es un guion que se
ejecuta igual todas las veces.

---

## Operar los dos ambientes en paralelo

Es una decisión razonable para evaluar antes de comprometerse. También introduce
un riesgo que conviene cerrar desde el primer día.

**El riesgo real no es técnico, es de gobierno del dato.** Dos instancias con
los mismos filtros pero fuentes actualizadas en momentos distintos muestran
cifras distintas del mismo mes. Si ambas URL circulan por correo, tarde o
temprano dos directivos citan números diferentes en la misma junta y el tablero
pierde credibilidad. El problema no aparece el primer mes: aparece el tercero,
cuando alguien actualiza un ambiente y olvida el otro.

### Cómo se cierra

**1. Un solo ambiente es el oficial.** El otro es de evaluación. Se declara por
escrito y se comunica junto con la URL.

**2. Etiquetar cada instancia.** El tablero muestra un distintivo en el
encabezado según la variable `ARCO_ENTORNO`:

```bash
# Ambiente oficial — sin distintivo visible
ARCO_ENTORNO=Producción

# Ambiente de evaluación — distintivo ámbar en el encabezado
ARCO_ENTORNO=Evaluación · Azure
```

Cualquier valor distinto de `Producción`, `Prod` u `Oficial` se marca como no
oficial, y la pestaña *Datos y supuestos* muestra una advertencia. Así, una
captura de pantalla de un ambiente de evaluación es reconocible como tal.

**3. Una sola URL en circulación.** La del ambiente oficial. La de evaluación se
comparte sólo con TI y con quienes participan en la prueba.

**4. Actualizar ambos el mismo día.** Si eso resulta pesado, es en sí mismo una
señal: el ambiente que cuesta mantener no es el que conviene conservar.

**5. Poner fecha de decisión.** Dos o tres cierres mensuales bastan. Operar dos
ambientes indefinidamente duplica el costo, el mantenimiento y la superficie
donde vive información financiera confidencial.

### Qué comparar durante la evaluación

| Criterio | Qué observar |
|---|---|
| Acceso desde fuera de la oficina | ¿La Dirección necesita consultarlo en viaje o desde el celular? Azure lo resuelve solo; el interno requiere VPN. |
| Política de datos | ¿Existe restricción formal de que los estados de resultados salgan de la red? Si la hay, no hay debate. |
| Carga para Contraloría | ¿Depositar los archivos resultó igual de simple en ambos? |
| Costo real | Azure ronda 56 USD mensuales; el interno usa infraestructura existente pero consume horas de TI. |
| Desempeño percibido | Tiempo de la primera carga y respuesta de los filtros con varios usuarios simultáneos. |
| Continuidad | ¿Quién lo levanta un domingo si se cae? |

Mi lectura, sin conocer sus políticas internas: si la Dirección necesita el
tablero fuera de la oficina y no hay restricción formal sobre los datos, Azure
gana por la autenticación con Entra ID y el certificado administrado. Si existe
esa restricción, el servidor interno no admite discusión y la evaluación sólo
sirve para confirmar que el desempeño alcanza.

---

## Lo común a cualquier ambiente

### El tablero no es un sitio estático

Necesita un proceso de Python ejecutándose permanentemente, un supervisor que lo
reinicie, y un proxy inverso que lo publique con certificado. Las tres piezas
están cubiertas en cada guía.

### Streamlit usa WebSockets

Si el proxy no reenvía las cabeceras `Upgrade` y `Connection`, el tablero carga
la pantalla pero se queda en *"Connecting..."* y no responde a los filtros. Es
la causa número uno de despliegues fallidos y parece un problema de la
aplicación cuando es del proxy. Las configuraciones de `deploy/` ya lo resuelven.

### Variables de entorno

| Variable | Para qué | Ejemplo |
|---|---|---|
| `ARCO_DATA_DIR` | Carpeta de los Excel, fuera del código | `/mnt/arco-datos` |
| `ARCO_ENTORNO` | Etiqueta del ambiente en el encabezado | `Producción` |

Separar datos de código es lo que permite que la actualización mensual no
requiera volver a desplegar.

### Los Excel no viajan en el repositorio

El `.gitignore` ya excluye `data/`. Contienen estados de resultados por plaza y
el detalle de deudores con nombre y saldo.

### Validar antes de publicar el dato

```bash
python scripts/validar_fuentes.py
```

Debe terminar en `Conciliación correcta.` Si no concilia, el problema está en
los datos, no en el despliegue.

---

## Docker

Para un servidor Linux o cualquier anfitrión con contenedores:

```bash
docker compose up -d --build
docker compose logs -f tablero
```

Queda en `http://<servidor>:8501`. Para publicarlo con dominio y certificado,
poner Nginx delante con `deploy/nginx-arco.conf`.

Para apuntar a un recurso de red, editar el volumen en `docker-compose.yml`:

```yaml
    volumes:
      - /mnt/fileserver/ARCO/Tablero/data/raw:/data/raw:ro
```

El montaje es de sólo lectura a propósito: refuerza en la infraestructura la
regla de que los archivos originales no se modifican.
