"""Corre la matriz de mediciones (plan B.4) con Playwright en un navegador REAL con ventana.

    uv run axial-bench bench_plan.json --browser msedge --profile A --out results/2026-12-01

- headless=False a proposito: en headless Chromium puede caer a SwiftShader (render por CPU) y
  los numeros no sirven. Cada JSON guarda la GPU reportada por WebGL
  (UNMASKED_RENDERER_WEBGL): es la evidencia de perfil A (integrada) vs B (dedicada). El
  cambio de GPU se hace a mano en "Configuracion de graficos" de Windows por ejecutable; este
  script solo registra cual quedo y avisa si detecta un renderer por software.
- Perfil A/B: en Chrome/Edge se fuerza la GPU con --force_low_power_gpu / --force_high_performance_gpu
  (usar --expect-gpu Intel / NVIDIA para cortar si quedo la otra).
- Chrome/Edge se lanzan sin vsync (--disable-gpu-vsync --disable-frame-rate-limit) y Firefox
  con layout.frame_rate = 0; si no, todas las configuraciones darian 60 FPS.
- Cada modo corre en una pagina nueva. Carga: `load_visits` visitas (la primera se descarta
  en el analisis), cada una con 1 carga en frio (cache: no-store) + `load_warm` en caliente.

Formato del plan (JSON):
{
  "base_url": "http://localhost:5173/",
  "api_url": "http://localhost:8000",
  "volumes": [
    {"key": "torso_sintetico", "url": "phantoms/torso_preview.nii.gz", "lod": "preview"},
    {"key": "torax", "study": "<uuid>", "lods": ["preview", "full"]}
  ],
  "modes": ["load", "fps", "capture"],
  "fps_configs": ["C0", "C1", "C2", "C3", "C4", "C3@1", "C3@2"],
  "fps_reps": 5,
  "load_visits": 10,
  "load_warm": 1,
  "capture_configs": "REF,C0,C1,C2,C3,C4,C3@1,C3@2",
  "timeout_s": 1800,
  "views": "bench/views.json"   (opcional; por defecto el del frontend)
}
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urljoin

from playwright.sync_api import Browser, Playwright, sync_playwright

SOFTWARE_RENDERERS = ("swiftshader", "llvmpipe", "basic render", "software")
CHROMIUM_ARGS = ["--disable-gpu-vsync", "--disable-frame-rate-limit", "--ignore-gpu-blocklist"]
FIREFOX_PREFS = {"layout.frame_rate": 0, "webgl.force-enabled": True}
# Laptops con dos GPU: Chromium/Edge eligen la GPU con estas banderas (verificado en Windows 11:
# Intel integrada vs RTX 3050). Firefox no tiene equivalente: ahi hay que fijarla en
# Configuracion > Pantalla > Graficos de Windows.
PROFILE_GPU_FLAGS = {"A": "--force_low_power_gpu", "B": "--force_high_performance_gpu"}


def login(api_url: str, email: str, password: str) -> str:
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["access_token"]


def launch(p: Playwright, browser: str, profile: str, select_gpu: bool) -> Browser:
    if browser == "firefox":
        return p.firefox.launch(headless=False, firefox_user_prefs=FIREFOX_PREFS)
    channel = {"msedge": "msedge", "chrome": "chrome", "chromium": None}[browser]
    args = list(CHROMIUM_ARGS)
    if select_gpu and profile in PROFILE_GPU_FLAGS:
        args.append(PROFILE_GPU_FLAGS[profile])
    return p.chromium.launch(headless=False, channel=channel, args=args)


def run_page(browser: Browser, url: str, timeout_s: float, log_path: Path) -> tuple[dict, dict]:
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    logs: list[str] = []
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
    try:
        page.goto(url)
        page.wait_for_function("window.__benchDone === true", timeout=timeout_s * 1000, polling=1000)
        result = page.evaluate("window.__benchResult")
        images = page.evaluate("window.__benchImages")
    finally:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(logs), encoding="utf-8")
        context.close()
    return result, images


def check_gpu(result: dict, expect: str | None) -> None:
    renderer = ((result.get("meta") or {}).get("gpu") or {}).get("renderer") or ""
    if any(s in renderer.lower() for s in SOFTWARE_RENDERERS):
        print(f"  !!! ATENCION: renderer por software ({renderer}). Estos numeros NO sirven.",
              file=sys.stderr)
    if expect and expect.lower() not in renderer.lower():
        raise SystemExit(f"La GPU reportada ({renderer}) no contiene '{expect}': perfil equivocado")


def save(folder: Path, name: str, result: dict, images: dict, runner: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if images:
        img_dir = folder / "capture"
        img_dir.mkdir(exist_ok=True)
        for file, data_url in images.items():
            (img_dir / file).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
        runner = runner | {"images_dir": "capture"}
    result["runner"] = runner
    (folder / f"{name}.json").write_text(json.dumps(result), encoding="utf-8")


def jobs(plan: dict):
    for vol in plan["volumes"]:
        lods = vol.get("lods") or [vol.get("lod", "preview")]
        for lod in lods:
            source = {"study": vol["study"], "lod": lod} if "study" in vol else {"url": vol["url"]}
            for mode in plan.get("modes", ["load", "fps", "capture"]):
                if mode == "load":
                    for visit in range(plan.get("load_visits", 10)):
                        yield vol["key"], lod, mode, f"load__v{visit:02d}", {
                            **source, "warm": plan.get("load_warm", 1)}, {"visit": visit}
                elif mode == "fps":
                    for cfg in plan.get("fps_configs", ["C0", "C1", "C2", "C3", "C4"]):
                        tag = cfg if "@" in cfg else f"{cfg}@0.5"
                        yield vol["key"], lod, mode, f"fps__{tag}", {
                            **source, "config": cfg, "reps": plan.get("fps_reps", 5)}, {"config": tag}
                elif mode == "capture":
                    yield vol["key"], lod, mode, "capture", {
                        **source, "configs": plan.get("capture_configs", "REF,C0,C1,C2,C3,C4")}, {}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--browser", choices=["msedge", "chrome", "chromium", "firefox"], required=True)
    parser.add_argument("--profile", required=True, help="perfil de hardware: A (integrada) o B (dedicada)")
    parser.add_argument("--out", type=Path, default=Path("results") / datetime.now().astimezone().strftime("%Y-%m-%d"))
    parser.add_argument("--token", default=os.environ.get("AXIAL_TOKEN"))
    parser.add_argument("--email", default=os.environ.get("AXIAL_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("AXIAL_PASSWORD"))
    parser.add_argument("--only-mode", choices=["load", "fps", "capture"])
    parser.add_argument("--skip-existing", action="store_true", help="no repetir JSON ya guardados")
    parser.add_argument("--no-gpu-flag", action="store_true",
                        help="no forzar la GPU por bandera (usar la de Windows)")
    parser.add_argument("--expect-gpu", default=None,
                        help="texto que debe aparecer en la GPU reportada (ej. Intel, NVIDIA); "
                             "si no aparece, se corta la corrida")
    args = parser.parse_args(argv)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    base_url = plan.get("base_url", "http://localhost:5173/")
    token = args.token
    if not token and args.email and any("study" in v for v in plan["volumes"]):
        token = login(plan.get("api_url", "http://localhost:8000"), args.email, args.password)

    with sync_playwright() as p:
        browser = launch(p, args.browser, args.profile, not args.no_gpu_flag)
        version = browser.version
        print(f"{args.browser} {version}, perfil {args.profile} -> {args.out}")
        for volume, lod, mode, name, params, extra in jobs(plan):
            if args.only_mode and mode != args.only_mode:
                continue
            folder = args.out / f"{args.browser}__{args.profile}" / f"{volume}__{lod}"
            if args.skip_existing and (folder / f"{name}.json").exists():
                continue
            query = {"bench": "1", "mode": mode, "label": f"{volume}/{lod}/{name}", **params}
            if plan.get("views"):
                query["views"] = plan["views"]
            if "study" in params:
                if not token:
                    raise SystemExit("Hace falta --token o --email/--password para volumenes del backend")
                query["token"] = token
            url = urljoin(base_url, "?" + urlencode(query))
            started = time.time()
            print(f"  {volume} {lod} {name} ...", end="", flush=True)
            result, images = run_page(browser, url, plan.get("timeout_s", 1800), folder / f"{name}.log")
            runner = {"browser": args.browser, "browserVersion": version, "profile": args.profile,
                      "volume": volume, "lod": lod, "mode": mode, "seconds": round(time.time() - started, 1),
                      **extra}
            save(folder, name, result, images or {}, runner)
            print(" ERROR: " + result["error"] if result.get("error") else f" ok ({runner['seconds']} s)")
            check_gpu(result, args.expect_gpu)
        browser.close()


if __name__ == "__main__":
    main()
