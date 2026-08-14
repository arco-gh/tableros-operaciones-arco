# Imagen del Tablero Ejecutivo ARCO.
# Los datos NO se incluyen en la imagen: se montan en tiempo de ejecución para
# que actualizar el mes no implique reconstruir ni volver a desplegar.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARCO_DATA_DIR=/data/raw

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY src/ ./src/
COPY components/ ./components/
COPY assets/ ./assets/
COPY scripts/ ./scripts/
COPY .streamlit/ ./.streamlit/

RUN mkdir -p /data/raw

# Usuario sin privilegios: el contenedor no necesita root para servir el tablero.
RUN useradd --create-home --uid 10001 arco && chown -R arco:arco /app /data
USER arco

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status==200 else 1)"

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
