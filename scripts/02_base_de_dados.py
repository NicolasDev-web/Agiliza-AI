"""Monta a base SQLite (data/processed/transporte.db) a partir de data/raw e data/ref."""
import sys

for _f in (sys.stdout, sys.stderr):   # Windows: o console padrão não é UTF-8 e acento vira "?"
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transporte import base  # noqa: E402

if __name__ == "__main__":
    t = time.time()
    print("Construindo a base...")
    base.construir(verbose=True)
    print(f"pronto em {time.time() - t:.1f}s: {base.CAMINHO} ({base.CAMINHO.stat().st_size / 1e6:.1f} MB)")
