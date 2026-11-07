"""Caminhos e constantes do projeto."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
DASHBOARD = ROOT / "dashboard"

# parametros.md: os portais foram exportados em 02/11/2026 às 06:00 (Brasília)
DATA_REFERENCIA = "2026-11-02"
# a integração com os portais começa em 03/09/2026; antes disso não há eventos
INICIO_PORTAIS = "2026-09-03"

TRANSPORTADORAS = ["Expressa Já", "TransNorte", "Rápido Sul", "ViaLog", "Correio Ágil"]
META_CUMPRIMENTO = 0.92  # politicas.csv
MIN_ENVIOS_PREFIXO = 30  # politicas.csv: prefixo com pelo menos 30 envios em 4 semanas
