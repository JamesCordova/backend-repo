"""Lectura de los JSON que produce el modo benchmark del frontend (schema axial-bench/1).

Estructura en disco que escribe run_bench.py:

    <resultados>/<navegador>__<perfil>/<volumen>__<lod>/
        load__v00.json ... load__v09.json      (una visita de pagina por archivo)
        fps__C0@0.5.json ...                   (5 repeticiones dentro de cada archivo)
        capture.json + capture/*.png

Cada JSON trae un bloque `runner` con navegador, version, perfil (A/B), volumen y lod.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BenchResult:
    path: Path
    data: dict

    @property
    def mode(self) -> str:
        return self.data["mode"]

    @property
    def runner(self) -> dict:
        return self.data.get("runner", {})

    def key(self) -> dict:
        r = self.runner
        gpu = (self.data.get("meta") or {}).get("gpu") or {}
        return {
            "volumen": r.get("volume", "?"),
            "lod": r.get("lod", "?"),
            "navegador": r.get("browser", "?"),
            "perfil": r.get("profile", "?"),
            "gpu": gpu.get("renderer") or "?",
        }


def config_tag(config: dict) -> str:
    step = float(config["stepVoxels"])
    return f"{config['id']}@{step:g}"


def load_results(root: Path) -> list[BenchResult]:
    out = []
    for path in sorted(Path(root).rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data.get("schema") == "axial-bench/1":
            out.append(BenchResult(path, data))
    return out
