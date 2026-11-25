"""Estadistica y SSIM con datos conocidos, y el analisis completo sobre JSON sinteticos."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy import stats as sps

from axial_tools import stats
from axial_tools.ssim import ssim_rgb


def test_median_iqr_known():
    assert stats.median_iqr([1, 2, 3, 4, 5]) == (3.0, 2.0, 4.0)


def test_bootstrap_ci_is_deterministic_and_contains_median():
    x = [28, 30, 31, 33, 35, 29, 32]
    lo, hi = stats.bootstrap_ci_median(x)
    assert lo <= np.median(x) <= hi
    assert (lo, hi) == stats.bootstrap_ci_median(x)
    assert stats.bootstrap_ci_median([7.0]) == (7.0, 7.0)


def test_frame_stats_constant_and_mixed():
    s = stats.frame_stats([10.0] * 100)
    assert s["fps_medio"] == pytest.approx(100)
    assert s["fps_mediana"] == pytest.approx(100)
    assert s["fps_p1"] == pytest.approx(100)
    assert s["fps_min"] == pytest.approx(100)
    s = stats.frame_stats([10.0] * 99 + [100.0])
    assert s["fps_min"] == pytest.approx(10)
    assert s["fps_medio"] == pytest.approx(1000 * 100 / (990 + 100))
    assert s["frame_ms_p99"] > 10


def test_pct_change():
    assert stats.pct_change(45, 30) == pytest.approx(50)
    assert np.isnan(stats.pct_change(10, 0))


def test_holm_matches_hand_computation():
    np.testing.assert_allclose(stats.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])


def test_friedman_matches_scipy_and_detects_order():
    rng = np.random.default_rng(0)
    blocks = {}
    for b in range(8):
        base = rng.normal(30, 3)
        blocks[(b,)] = {t: base + i * 5 + rng.normal(0, 0.5) for i, t in enumerate(stats.MAIN_CONFIGS)}
    f = stats.friedman(blocks, stats.MAIN_CONFIGS)
    expected = sps.friedmanchisquare(*[[blk[t] for blk in blocks.values()] for t in stats.MAIN_CONFIGS])
    assert f["estadistico"] == pytest.approx(expected.statistic)
    assert f["p"] == pytest.approx(expected.pvalue)
    assert f["significativo"]
    pairs = stats.wilcoxon_pairs(blocks, stats.MAIN_CONFIGS)
    assert len(pairs) == 10 and all(p["p_holm"] >= p["p"] for p in pairs)


def test_friedman_ignores_incomplete_blocks():
    blocks = {(1,): {"C0@0.5": 1, "C1@0.5": 2}, (2,): {t: 1.0 for t in stats.MAIN_CONFIGS}}
    assert stats.friedman(blocks, stats.MAIN_CONFIGS)["bloques"] == 1


def test_ssim_identical_and_noisy():
    rng = np.random.default_rng(1)
    ramp = np.linspace(0, 255, 64)
    img = np.stack([np.add.outer(ramp, ramp) / 2] * 3, axis=2).astype(np.uint8)  # imagen suave
    assert ssim_rgb(img, img) == pytest.approx(1.0)
    noisy = np.clip(img.astype(int) + rng.integers(-40, 40, img.shape), 0, 255).astype(np.uint8)
    assert ssim_rgb(img, noisy) < 0.9


# --- analisis completo ---------------------------------------------------------------------------

def _runner(volume, lod, mode, **extra):
    return {"browser": "msedge", "browserVersion": "1", "profile": "A" if lod == "preview" else "B",
            "volume": volume, "lod": lod, "mode": mode, **extra}


def _meta():
    return {"gpu": {"renderer": "GPU de prueba"}}


def _write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def results(tmp_path) -> Path:
    root = tmp_path / "res"
    rng = np.random.default_rng(2)
    for lod, base_fps in (("preview", 40.0), ("full", 20.0)):
        folder = root / f"msedge__{'A' if lod == 'preview' else 'B'}" / f"torso__{lod}"
        for i, cfg in enumerate(["C0", "C1", "C2", "C3", "C4"]):
            fps = base_fps * (1 + 0.25 * i)
            runs = [{"rep": r, "frameMs": list(1000 / (fps + rng.normal(0, 0.5, 300))), "t": [],
                     "summary": {}} for r in range(5)]
            _write(folder / f"fps__{cfg}@0.5.json", {
                "schema": "axial-bench/1", "mode": "fps", "meta": _meta(),
                "config": {"id": cfg, "stepVoxels": 0.5}, "runs": runs,
                "runner": _runner("torso", lod, "fps")})
        for v in range(10):
            _write(folder / f"load__v{v:02d}.json", {
                "schema": "axial-bench/1", "mode": "load", "meta": _meta(),
                "loads": [{"cold": True, "totalMs": 5000 + 100 * v, "marks": {"primer_fotograma": 5000},
                           "bytes": 1_000_000, "transferSize": 1_000_500, "textureBytes": 2_000_000,
                           "voxels": 1_000_000, "dims": [100, 100, 100]},
                          {"cold": False, "totalMs": 900, "marks": {}, "bytes": 1, "transferSize": 0,
                           "textureBytes": 2_000_000, "voxels": 1_000_000, "dims": [100, 100, 100]}],
                "runner": _runner("torso", lod, "load", visit=v)})
        img = (rng.random((32, 32, 3)) * 255).astype(np.uint8)
        caps = []
        (folder / "capture").mkdir(parents=True, exist_ok=True)
        for view in ("anterior", "lateral"):
            for cfg, step, noise in (("REF", 0.25, 0), ("C0", 0.5, 2), ("C4", 0.5, 4)):
                name = f"{view}__{cfg}@{step}.png"
                shot = np.clip(img.astype(int) + rng.integers(-noise, noise + 1, img.shape), 0, 255)
                Image.fromarray(shot.astype(np.uint8)).save(folder / "capture" / name)
                caps.append({"view": view, "config": cfg, "stepVoxels": step, "file": name})
        _write(folder / "capture.json", {"schema": "axial-bench/1", "mode": "capture", "meta": _meta(),
                                         "captures": caps,
                                         "runner": _runner("torso", lod, "capture", images_dir="capture")})
    return root


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_full_analysis(results):
    tables = stats.analyze(results)
    out = results / "analisis"
    for name in ("tabla_fps", "tabla_carga", "tabla_ssim", "pruebas_friedman", "hipotesis"):
        assert (out / f"{name}.csv").exists()

    fps = {(t["lod"], t["config"]): t for t in tables["tabla_fps"]}
    assert fps[("preview", "C0@0.5")]["fps_mediana"] == pytest.approx(40, rel=0.02)
    assert fps[("preview", "C4@0.5")]["cambio_pct_vs_C0"] == pytest.approx(100, abs=3)
    assert fps[("preview", "C4@0.5")]["repeticiones"] == 5
    assert fps[("preview", "C4@0.5")]["ssim_min"] is not None

    cold = next(t for t in tables["tabla_carga"] if t["tipo"] == "frio" and t["lod"] == "preview")
    assert cold["n"] == 9  # se descarta la primera visita
    assert cold["mediana_ms"] == pytest.approx(5500)
    assert cold["cumple"] is True

    friedman = {r["comparacion"]: r for r in tables["pruebas_friedman"]}
    assert friedman["configuraciones (todas las condiciones)"]["significativo"]

    hyp = tables["hipotesis"]
    # preview A: C4 = 40*2 = 80 FPS cumple; full B: 20*2 = 40 FPS cumple; SSIM alto
    assert hyp[-1]["criterio"].startswith("HIPOTESIS") and hyp[-1]["cumple"] is True
    assert len(_read(out / "ssim_por_vista.csv")) == 8
