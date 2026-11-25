"""SSIM de cada captura frente a la visualizacion de referencia (REF: sin aceleracion, Δs 0,25).

Decision fija para toda la tesis: SSIM sobre RGB (promedio de los 3 canales), ventana
uniforme de 7x7 (valores por defecto de scikit-image), data_range = 255, imagenes PNG de
1024x1024 capturadas en reposo con la misma vista, FT, contraste y recorte.

Uso:
    uv run axial-ssim results/2026-12-01 --out results/2026-12-01/analisis
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from axial_tools.results import load_results

REF_TAG = "REF@0.25"


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def ssim_rgb(reference: np.ndarray, image: np.ndarray) -> float:
    if reference.shape != image.shape:
        raise ValueError(f"tamanos distintos: {reference.shape} vs {image.shape}")
    return float(structural_similarity(reference, image, channel_axis=2, data_range=255))


def ssim_rows(root: Path) -> list[dict]:
    rows: list[dict] = []
    for result in load_results(root):
        if result.mode != "capture" or "captures" not in result.data:
            continue
        images_dir = result.path.parent / result.runner.get("images_dir", "capture")
        by_view: dict[str, dict[str, Path]] = {}
        for cap in result.data["captures"]:
            tag = f"{cap['config']}@{float(cap['stepVoxels']):g}"
            by_view.setdefault(cap["view"], {})[tag] = images_dir / cap["file"]
        for view, shots in by_view.items():
            if REF_TAG not in shots:
                continue
            ref = load_rgb(shots[REF_TAG])
            for tag, path in sorted(shots.items()):
                if tag == REF_TAG:
                    continue
                rows.append({**result.key(), "vista": view, "config": tag,
                             "ssim": round(ssim_rgb(ref, load_rgb(path)), 6)})
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    """Media y minimo del SSIM por condicion (todas las vistas)."""
    groups: dict[tuple, list[float]] = {}
    for r in rows:
        k = (r["volumen"], r["lod"], r["navegador"], r["perfil"], r["config"])
        groups.setdefault(k, []).append(r["ssim"])
    out = []
    for (vol, lod, nav, perfil, cfg), values in sorted(groups.items()):
        out.append({"volumen": vol, "lod": lod, "navegador": nav, "perfil": perfil, "config": cfg,
                    "vistas": len(values), "ssim_media": round(float(np.mean(values)), 4),
                    "ssim_min": round(float(np.min(values)), 4),
                    "cumple_0_85": bool(np.min(values) >= 0.85)})
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or args.results / "analisis"
    rows = ssim_rows(args.results)
    write_csv(out / "ssim_por_vista.csv", rows)
    summary = summarize(rows)
    write_csv(out / "tabla_ssim.csv", summary)
    for s in summary:
        print(f"{s['volumen']:>20} {s['lod']:>8} {s['config']:>10}  media {s['ssim_media']:.4f}  "
              f"min {s['ssim_min']:.4f}")
    print(f"{len(rows)} comparaciones -> {out}")


if __name__ == "__main__":
    main()
