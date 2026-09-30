FROM python:3.12-slim

WORKDIR /app

# Instala dependências Python antes de copiar o código (melhor cache de layers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia apenas o código fonte (data/ e logs/ são volumes)
COPY src/ ./src/

RUN mkdir -p data/processed data/cpap_sd data/Smartband logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "src.visualization.app:app", "--host", "0.0.0.0", "--port", "8000"]
