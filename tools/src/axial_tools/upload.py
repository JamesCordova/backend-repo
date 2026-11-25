"""Sube los datos reales al backend por los mismos endpoints que usa el frontend.

DICOM: un PUT por archivo + confirmar-subida. RAW: PUT + confirmar-subida-raw con los parametros
conocidos. Espera a que cada estudio quede `ready` (o `failed`) y escribe `studies.json`
(id del dataset -> id del estudio), que es lo que usan los planes de medicion.

    uv run axial-upload --api http://localhost:8000 --datasets out/datasets_cache \
        --only tcia_lidc_0001,tcia_pancreas_0051,klacansky_stent --out out/studies.json

El usuario de medicion se crea si no existe; las credenciales quedan en out/ (ignorado por git).
"""

from __future__ import annotations

import argparse
import json
import secrets
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from axial_tools.datasets import by_id

# RAW con parametros conocidos (de su .nhdr). value_range: ventana en los valores almacenados
# que equivale a HU [-1000, 1000] -- la misma que el backend usa para DICOM, asi el frontend
# interpreta igual ambos caminos.
RAW_PARAMS = {
    "klacansky_stent": {"file": "stent_512x512x174_uint16.raw", "dims": [174, 512, 512],
                        "dtype": "uint16", "spacing": [3.2, 0.8398, 0.8398], "value_range": [24, 2024]},
}


class Api:
    def __init__(self, base: str, token: str | None = None):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body=None, data: bytes | None = None,
             content_type: str | None = None):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            data = json.dumps(body).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None

    def put_file(self, study_id: str, path: Path) -> None:
        boundary = uuid.uuid4().hex
        payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                   f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        payload += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        self.call("PUT", f"/estudios/{study_id}/archivos/{path.name}", data=payload,
                  content_type=f"multipart/form-data; boundary={boundary}")


def ensure_user(api: Api, creds_path: Path) -> str:
    if creds_path.exists():
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
    else:
        creds = {"name": "Medicion Axial", "email": "medicion@axial-tesis.dev",
                 "password": secrets.token_urlsafe(16)}
        try:
            api.call("POST", "/auth/registro", body=creds)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"No se pudo registrar el usuario de medicion ({exc.code}); "
                             f"borra {creds_path} o usa otra base") from exc
        creds_path.parent.mkdir(parents=True, exist_ok=True)
        creds_path.write_text(json.dumps(creds), encoding="utf-8")
    return api.call("POST", "/auth/login", body={"email": creds["email"], "password": creds["password"]})[
        "access_token"]


def wait_ready(api: Api, study_id: str, timeout_s: float = 1800) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        study = api.call("GET", f"/estudios/{study_id}")
        if study["status"] in ("ready", "failed"):
            return study
        time.sleep(2)
    raise TimeoutError(study_id)


def upload(api: Api, dataset_id: str, cache: Path) -> dict:
    ds = by_id(dataset_id)
    study = api.call("POST", "/estudios", body={"name": f"{dataset_id} ({ds.region})"})
    sid = study["id"]
    started = time.time()
    if ds.kind in ("dicom", "dicom_from"):
        files = sorted((cache / dataset_id / "dicom").glob("*.dcm"))
        if not files:
            raise SystemExit(f"{dataset_id}: no hay DICOM en cache; corre axial-datasets fetch primero")
        for f in files:
            api.put_file(sid, f)
        api.call("POST", f"/estudios/{sid}/confirmar-subida", body={"filenames": [f.name for f in files]})
    elif dataset_id in RAW_PARAMS:
        p = RAW_PARAMS[dataset_id]
        api.put_file(sid, cache / dataset_id / p["file"])
        api.call("POST", f"/estudios/{sid}/confirmar-subida-raw", body={
            "filename": p["file"], "dims": p["dims"], "dtype": p["dtype"], "spacing": p["spacing"],
            "value_range": p["value_range"]})
    else:
        raise SystemExit(f"{dataset_id}: el backend solo acepta DICOM o RAW (NIfTI pendiente, plan E.5)")
    uploaded = time.time()
    final = wait_ready(api, sid)
    return {"study_id": sid, "status": final["status"], "error": final.get("error_message"),
            "upload_s": round(uploaded - started, 1), "processing_s": round(time.time() - uploaded, 1),
            "region": ds.region}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--datasets", type=Path, default=Path("out/datasets_cache"))
    parser.add_argument("--only", required=True, help="ids del catalogo, separados por coma")
    parser.add_argument("--out", type=Path, default=Path("out/studies.json"))
    parser.add_argument("--creds", type=Path, default=Path("out/backend_user.json"))
    args = parser.parse_args(argv)

    api = Api(args.api)
    api.token = ensure_user(api, args.creds)
    studies = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    for dataset_id in args.only.split(","):
        print(f"{dataset_id} ...", end="", flush=True)
        studies[dataset_id] = upload(api, dataset_id, args.datasets)
        s = studies[dataset_id]
        print(f" {s['status']} (subida {s['upload_s']} s, procesamiento {s['processing_s']} s)"
              + (f" ERROR: {s['error']}" if s["error"] else ""))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(studies, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
