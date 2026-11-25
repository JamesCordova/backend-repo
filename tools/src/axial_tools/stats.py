"""Estadistica del rendimiento (Tablas 13 y 14 de la tesis).

Lee los JSON del modo benchmark y escribe en <resultados>/analisis/:

  fps_repeticiones.csv   una fila por repeticion de la trayectoria
  tabla_fps.csv          una fila por condicion (volumen x lod x navegador x perfil x config):
                         FPS medio, mediana, percentil 1 de FPS (= percentil 99 del tiempo de
                         fotograma, tambien reportado), minimo, IC 95 % de la mediana (bootstrap
                         sobre las medianas por repeticion), cambio % de la mediana vs C0 y SSIM
  tabla_carga.csv        tiempo de carga por condicion (frio/caliente), mediana, RIC, IC 95 %
  pruebas_friedman.csv   Friedman entre configuraciones C0..C4 (y entre navegadores)
  pruebas_wilcoxon.csv   Wilcoxon por pares con correccion de Holm (alfa = 0,05)
  hipotesis.csv          criterio de aceptacion de la hipotesis con C4

Uso:
    uv run axial-stats results/2026-12-01
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
from scipy import stats as sps
from statsmodels.stats.multitest import multipletests

from axial_tools.results import BenchResult, config_tag, load_results
from axial_tools.ssim import ssim_rows, write_csv
from axial_tools.ssim import summarize as summarize_ssim

ALPHA = 0.05
MAIN_CONFIGS = ["C0@0.5", "C1@0.5", "C2@0.5", "C3@0.5", "C4@0.5"]
LOAD_LIMIT_MS = {"preview": 10_000, "full": 30_000}
FPS_THRESHOLD = 30.0
SSIM_THRESHOLD = 0.85
# Condiciones de la hipotesis (Tabla 13): preview con perfil A, full con perfil B.
HYPOTHESIS_CONDITIONS = [("preview", "A"), ("full", "B")]


# --- estadisticos basicos ----------------------------------------------------------------------

def median_iqr(values) -> tuple[float, float, float]:
    x = np.asarray(values, float)
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return float(med), float(q1), float(q3)


def bootstrap_ci_median(values, n_boot: int = 10_000, alpha: float = ALPHA,
                        seed: int = 12345) -> tuple[float, float]:
    """IC percentil de la mediana. Con n < 2 devuelve (valor, valor)."""
    x = np.asarray(values, float)
    if x.size < 2:
        v = float(x[0]) if x.size else float("nan")
        return v, v
    rng = np.random.default_rng(seed)
    samples = rng.choice(x, size=(n_boot, x.size), replace=True)
    medians = np.median(samples, axis=1)
    lo, hi = np.percentile(medians, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def frame_stats(frame_ms) -> dict:
    """FPS a partir de los tiempos de fotograma (ms)."""
    ms = np.asarray(frame_ms, float)
    ms = ms[ms > 0]
    fps = 1000.0 / ms
    return {
        "fotogramas": int(ms.size),
        "fps_medio": float(1000.0 * ms.size / ms.sum()),
        "fps_mediana": float(np.median(fps)),
        "fps_p1": float(np.percentile(fps, 1)),
        "frame_ms_p99": float(np.percentile(ms, 99)),
        "fps_min": float(fps.min()),
    }


def pct_change(value: float, base: float) -> float:
    return float("nan") if not base else 100.0 * (value - base) / base


def holm(pvalues) -> np.ndarray:
    p = np.asarray(pvalues, float)
    if p.size == 0:
        return p
    return multipletests(p, alpha=ALPHA, method="holm")[1]


def friedman(blocks: dict[tuple, dict[str, float]], treatments: list[str]) -> dict:
    """Friedman con los bloques completos (todos los tratamientos presentes)."""
    complete = [b for b in blocks.values() if all(t in b for t in treatments)]
    result = {"tratamientos": " vs ".join(treatments), "bloques": len(complete),
              "estadistico": float("nan"), "p": float("nan")}
    if len(treatments) >= 3 and len(complete) >= 2:
        columns = [[b[t] for b in complete] for t in treatments]
        stat, p = sps.friedmanchisquare(*columns)
        result.update(estadistico=float(stat), p=float(p))
    result["significativo"] = bool(result["p"] < ALPHA)
    return result


def wilcoxon_pairs(blocks: dict[tuple, dict[str, float]], treatments: list[str]) -> list[dict]:
    rows = []
    for a, b in itertools.combinations(treatments, 2):
        pairs = [(blk[a], blk[b]) for blk in blocks.values() if a in blk and b in blk]
        row = {"a": a, "b": b, "n": len(pairs), "estadistico": float("nan"), "p": float("nan")}
        if len(pairs) >= 2:
            x, y = np.array(pairs).T
            if np.any(x != y):
                res = sps.wilcoxon(x, y, zero_method="wilcox")
                row.update(estadistico=float(res.statistic), p=float(res.pvalue))
        rows.append(row)
    valid = [r for r in rows if not np.isnan(r["p"])]
    for r, ph in zip(valid, holm([r["p"] for r in valid])):
        r["p_holm"] = float(ph)
    for r in rows:
        r.setdefault("p_holm", float("nan"))
        r["significativo"] = bool(r["p_holm"] < ALPHA)
    return rows


# --- tablas --------------------------------------------------------------------------------------

def _cond(key: dict) -> tuple:
    return key["volumen"], key["lod"], key["navegador"], key["perfil"]


def fps_tables(results: list[BenchResult], ssim_summary: list[dict]) -> tuple[list[dict], list[dict]]:
    reps: list[dict] = []
    pooled: dict[tuple, dict] = {}
    for r in results:
        if r.mode != "fps" or "runs" not in r.data:
            continue
        key = r.key()
        tag = config_tag(r.data["config"])
        g = pooled.setdefault((*_cond(key), tag), {"key": key, "frames": [], "rep_medians": [],
                                                   "vsync": False})
        for run in r.data["runs"]:
            s = frame_stats(run["frameMs"])
            vsync = bool(run.get("summary", {}).get("possiblyVsyncCapped", False))
            reps.append({**key, "config": tag, "rep": run["rep"], **_round(s), "vsync_sospechoso": vsync})
            g["frames"].extend(run["frameMs"])
            g["rep_medians"].append(s["fps_mediana"])
            g["vsync"] |= vsync

    ssim_index = {(s["volumen"], s["lod"], s["navegador"], s["perfil"], s["config"]): s
                  for s in ssim_summary}
    table = []
    for (vol, lod, nav, perfil, tag), g in sorted(pooled.items()):
        s = frame_stats(g["frames"])
        med, q1, q3 = median_iqr(g["rep_medians"])
        lo, hi = bootstrap_ci_median(g["rep_medians"])
        ss = ssim_index.get((vol, lod, nav, perfil, tag), {})
        table.append({
            **g["key"], "config": tag, "repeticiones": len(g["rep_medians"]), **_round(s),
            "fps_mediana_rep": round(med, 2), "fps_ric_q1": round(q1, 2), "fps_ric_q3": round(q3, 2),
            "fps_ic95_inf": round(lo, 2), "fps_ic95_sup": round(hi, 2),
            "ssim_media": ss.get("ssim_media"), "ssim_min": ss.get("ssim_min"),
            "vsync_sospechoso": g["vsync"],
        })
    base = {(_cond(t)[:4], t["config"]): t["fps_mediana"] for t in table}
    for t in table:
        c0 = base.get((_cond(t)[:4], "C0@0.5"))
        t["cambio_pct_vs_C0"] = round(pct_change(t["fps_mediana"], c0), 1) if c0 else None
    return reps, table


def load_table(results: list[BenchResult]) -> tuple[list[dict], list[dict]]:
    rows = []
    for r in results:
        if r.mode != "load" or "loads" not in r.data:
            continue
        visit = r.runner.get("visit", 0)
        for ld in r.data["loads"]:
            marks = ld.get("marks", {})
            rows.append({**r.key(), "visita": visit, "tipo": "frio" if ld["cold"] else "caliente",
                         "total_ms": ld["totalMs"], **{f"marca_{k}": v for k, v in marks.items()},
                         "bytes": ld.get("bytes"), "transfer_size": ld.get("transferSize"),
                         "textura_bytes": ld.get("textureBytes"), "voxeles": ld.get("voxels"),
                         "dims": "x".join(str(d) for d in ld.get("dims", []))})
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((*_cond(row), row["tipo"]), []).append(row)
    table = []
    for (vol, lod, nav, perfil, tipo), items in sorted(groups.items()):
        # 10 visitas por condicion; la primera se descarta como calentamiento.
        kept = [i for i in items if i["visita"] != min(x["visita"] for x in items)] or items
        values = [i["total_ms"] for i in kept]
        med, q1, q3 = median_iqr(values)
        lo, hi = bootstrap_ci_median(values)
        limit = LOAD_LIMIT_MS.get(lod)
        table.append({
            "volumen": vol, "lod": lod, "navegador": nav, "perfil": perfil, "tipo": tipo,
            "n": len(values), "mediana_ms": round(med, 1), "ric_q1_ms": round(q1, 1),
            "ric_q3_ms": round(q3, 1), "ic95_inf_ms": round(lo, 1), "ic95_sup_ms": round(hi, 1),
            "mb_transferidos": round((kept[0]["transfer_size"] or kept[0]["bytes"] or 0) / 1e6, 2),
            "memoria_textura_mb": round((kept[0]["textura_bytes"] or 0) / 1e6, 2),
            "dims": kept[0]["dims"], "voxeles": kept[0]["voxeles"],
            "limite_ms": limit if tipo == "frio" else None,
            "cumple": (med <= limit) if (tipo == "frio" and limit) else None,
        })
    return rows, table


def inferential(reps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Friedman + Wilcoxon/Holm entre configuraciones y entre navegadores."""
    friedman_rows, wilcoxon_rows = [], []

    def run(name: str, blocks: dict, treatments: list[str]) -> None:
        f = friedman(blocks, treatments)
        friedman_rows.append({"comparacion": name, **f})
        for w in wilcoxon_pairs(blocks, treatments):
            wilcoxon_rows.append({"comparacion": name, "friedman_significativo": f["significativo"], **w})

    # Configuraciones: bloque = (volumen, lod, navegador, perfil, repeticion)
    def config_blocks(rows):
        blocks: dict[tuple, dict] = {}
        for r in rows:
            if r["config"] in MAIN_CONFIGS:
                blocks.setdefault((*_cond(r), r["rep"]), {})[r["config"]] = r["fps_mediana"]
        return blocks

    run("configuraciones (todas las condiciones)", config_blocks(reps), MAIN_CONFIGS)
    strata = sorted({(r["lod"], r["perfil"]) for r in reps})
    for lod, perfil in strata:
        subset = [r for r in reps if r["lod"] == lod and r["perfil"] == perfil]
        run(f"configuraciones ({lod}, perfil {perfil})", config_blocks(subset), MAIN_CONFIGS)

    # Navegadores: bloque = (volumen, lod, perfil, config, repeticion)
    browsers = sorted({r["navegador"] for r in reps})
    if len(browsers) >= 2:
        blocks: dict[tuple, dict] = {}
        for r in reps:
            blocks.setdefault((r["volumen"], r["lod"], r["perfil"], r["config"], r["rep"]), {})[
                r["navegador"]] = r["fps_mediana"]
        if len(browsers) >= 3:
            run("navegadores", blocks, browsers)
        else:
            for w in wilcoxon_pairs(blocks, browsers):
                wilcoxon_rows.append({"comparacion": "navegadores", "friedman_significativo": None, **w})
    return friedman_rows, wilcoxon_rows


def hypothesis(fps_table: list[dict], ssim_summary: list[dict]) -> list[dict]:
    rows = []
    for lod, perfil in HYPOTHESIS_CONDITIONS:
        for t in fps_table:
            if t["config"] == "C4@0.5" and t["lod"] == lod and t["perfil"] == perfil:
                rows.append({"criterio": f"mediana FPS C4 >= {FPS_THRESHOLD:g} ({lod}, perfil {perfil})",
                             "volumen": t["volumen"], "navegador": t["navegador"],
                             "valor": t["fps_mediana"], "cumple": t["fps_mediana"] >= FPS_THRESHOLD})
    for s in ssim_summary:
        if s["config"] == "C4@0.5":
            rows.append({"criterio": f"SSIM C4 >= {SSIM_THRESHOLD} en todas las vistas",
                         "volumen": s["volumen"], "navegador": s["navegador"],
                         "valor": s["ssim_min"], "cumple": s["ssim_min"] >= SSIM_THRESHOLD})
    if rows:
        rows.append({"criterio": "HIPOTESIS (todos los criterios)", "volumen": "*", "navegador": "*",
                     "valor": None, "cumple": all(r["cumple"] for r in rows)})
    return rows


def _round(d: dict) -> dict:
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in d.items()}


def analyze(root: Path, out: Path | None = None) -> dict[str, list[dict]]:
    out = out or root / "analisis"
    results = load_results(root)
    ssim_detail = ssim_rows(root)
    ssim_summary = summarize_ssim(ssim_detail)
    reps, fps = fps_tables(results, ssim_summary)
    load_rows, loads = load_table(results)
    fr, wl = inferential(reps)
    hyp = hypothesis(fps, ssim_summary)
    tables = {
        "fps_repeticiones": reps, "tabla_fps": fps, "cargas": load_rows, "tabla_carga": loads,
        "ssim_por_vista": ssim_detail, "tabla_ssim": ssim_summary, "pruebas_friedman": fr,
        "pruebas_wilcoxon": wl, "hipotesis": hyp,
    }
    for name, rows in tables.items():
        write_csv(out / f"{name}.csv", rows)
    return tables


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    tables = analyze(args.results, args.out)
    for t in tables["tabla_fps"]:
        print(f"{t['volumen']:>16} {t['lod']:>8} {t['navegador']:>8} {t['perfil']:>2} {t['config']:>8}"
              f"  mediana {t['fps_mediana']:7.1f} FPS  p1 {t['fps_p1']:6.1f}  "
              f"cambio {t['cambio_pct_vs_C0']}%  SSIM min {t['ssim_min']}")
    for t in tables["tabla_carga"]:
        print(f"carga {t['volumen']:>16} {t['lod']:>8} {t['tipo']:>9}: mediana {t['mediana_ms']} ms "
              f"(n={t['n']}) cumple={t['cumple']}")
    for h in tables["hipotesis"]:
        print(f"{h['criterio']}: {h['volumen']} -> {h['valor']} cumple={h['cumple']}")
    print(f"CSV en {(args.out or args.results / 'analisis').resolve()}")


if __name__ == "__main__":
    main()
