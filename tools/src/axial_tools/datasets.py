"""Datos reales abiertos para validar y medir (Tabla 11/12 de la tesis).

Catalogo reproducible: de donde sale cada volumen, licencia, region, formato y como pasarlo a
NIfTI (RAS, con la afin correcta). Descarga con cache, convierte y opcionalmente genera los
niveles isotropicos preview (4 mm) y full (1 mm) como los del backend.

    uv run axial-datasets list
    uv run axial-datasets fetch --out out/datasets                  # todo el catalogo
    uv run axial-datasets fetch --only slicer_ct_chest,tcia_lidc_0001 --lods
    uv run axial-datasets fetch --out ../../volume-renderer-ts/public/datasets --lods

Fuentes (verificadas el 2026-11-25; ver la licencia de cada una antes de publicar imagenes):
- klacansky.com/open-scivis-datasets (RAW + NHDR; solo por http, el https rechaza conexion)
- volume.open-terrain.org (PVM comprimido con DDS; el certificado https no coincide, se usa http)
- github.com/neurolabusc/niivue-images (NIfTI CT, referenciado por volume-renderer)
- github.com/Slicer/SlicerTestingData (NRRD CT de los datos de ejemplo de 3D Slicer)
- TCIA (DICOM, API publica NBIA sin login; colecciones CC BY)

Los lectores de NRRD y de PVM/DDS son implementaciones propias a partir de la descripcion de los
formatos (no se copia codigo GPL de V^3).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

from axial_tools.reference import LPS_TO_RAS, read_dicom_series

TCIA_IMAGE = "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage?SeriesInstanceUID="
KLACANSKY = "http://klacansky.com/open-scivis-datasets/"
OPEN_TERRAIN = "http://volume.open-terrain.org/"
NIIVUE = "https://github.com/neurolabusc/niivue-images/raw/main/"
SLICER = "https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/"


@dataclass(frozen=True)
class Dataset:
    id: str
    region: str  # cabeza | torax | abdomen | otro
    kind: str  # nifti | nrrd | nhdr | pvm | dicom
    url: str
    description: str
    source: str
    license: str
    roles: tuple[str, ...] = ()  # medicion, validacion, dicom, raw, pvm, no_axial
    # Como pasar los valores almacenados a HU: hu = valor + hu_offset (None = no son HU)
    hu_offset: float | None = 0.0
    extra_urls: tuple[str, ...] = ()
    notes: str = ""


CATALOG: list[Dataset] = [
    # --- NIfTI CT reales en HU ------------------------------------------------------------------
    Dataset("niivue_ct_abdo", "abdomen", "nifti", NIIVUE + "CT_Abdo.nii.gz",
            "CTA toraco-abdominal (Slicer CTA-cardio)", "neurolabusc/niivue-images (Steve Pieper)",
            "ver niivue-images/README (datos de ejemplo de 3D Slicer)", ("medicion", "validacion")),
    Dataset("niivue_ct_avm", "cabeza", "nifti", NIIVUE + "CT_AVM.nii.gz",
            "CT de cabeza con malformacion arteriovenosa", "neurolabusc/niivue-images (PRISM/IBIS)",
            "ver niivue-images/README", ("validacion",), hu_offset=None,
            notes="valores en [0, 563]: no son HU (ya ventaneado)"),
    Dataset("niivue_ct_philips", "cabeza", "nifti", NIIVUE + "CT_Philips.nii.gz",
            "CT Philips (ejemplo de dcm2nii)", "neurolabusc/niivue-images", "ver niivue-images/README",
            ("validacion",)),
    Dataset("niivue_ct_pitch", "cabeza", "nifti", NIIVUE + "CT_pitch.nii.gz",
            "CT adquirido rotado respecto del gantry (afin oblicua)", "neurolabusc/niivue-images",
            "ver niivue-images/README", ("validacion", "no_axial"), hu_offset=None,
            notes="8 bit [0, 255], no HU; sirve para ver el aviso de afin oblicua del cargador"),
    Dataset("slicer_ct_chest", "torax", "nrrd",
            SLICER + "4507b664690840abb6cb9af2d919377ffc4ef75b167cb6fd0f747befdb12e38e",
            "CT de torax (CTChest de 3D Slicer)", "Slicer SampleData", "datos de ejemplo de 3D Slicer",
            ("medicion", "validacion")),
    # --- DICOM reales (TCIA, CC BY) -------------------------------------------------------------
    Dataset("tcia_lidc_0001", "torax", "dicom",
            TCIA_IMAGE + "1.3.6.1.4.1.14519.5.2.1.6279.6001.179049373636438705059720603192",
            "CT de torax, 133 cortes (LIDC-IDRI-0001)", "TCIA LIDC-IDRI", "CC BY 3.0",
            ("dicom", "medicion", "validacion")),
    Dataset("tcia_pancreas_0051", "abdomen", "dicom",
            TCIA_IMAGE + "1.2.826.0.1.3680043.2.1125.1.77419915248783746629465382576486048",
            "CT abdominal con contraste, 185 cortes (Pancreas-CT PANCREAS_0051)", "TCIA Pancreas-CT",
            "CC BY 3.0", ("dicom", "medicion", "validacion")),
    Dataset("tcia_cptac_head_cor", "cabeza", "dicom",
            TCIA_IMAGE + "1.3.6.1.4.1.14519.5.2.1.1427.3349.112299006248001330093944099964",
            "CT de cabeza reformateado en plano CORONAL, 112 cortes (CPTAC-AML C3L-05387)",
            "TCIA CPTAC-AML", "CC BY 4.0", ("dicom", "no_axial", "validacion"),
            notes="CP-F06: serie no axial real"),
    Dataset("cabeza_philips_dicom", "cabeza", "dicom_from", "niivue_ct_philips",
            "CT de cabeza completo (CT_Philips) reescrito como serie DICOM axial",
            "derivado de neurolabusc/niivue-images", "ver niivue-images/README",
            ("dicom", "medicion"),
            notes="voxeles reales, contenedor DICOM generado por axial-datasets (no hay una "
                  "serie de cabeza completa publica por la API de TCIA): solo para medir el "
                  "camino DICOM del backend, no para validar la lectura DICOM"),
    # --- RAW con parametros conocidos (klacansky) -----------------------------------------------
    Dataset("klacansky_stent", "abdomen", "nhdr", KLACANSKY + "stent/stent.nhdr",
            "CT de abdomen y pelvis con stent aortico, uint16 512x512x174",
            "klacansky / volvis.org (Viatronix)", "ver open-scivis-datasets", ("raw", "medicion"),
            hu_offset=-1024.0, extra_urls=(KLACANSKY + "stent/stent_512x512x174_uint16.raw",)),
    Dataset("klacansky_pancreas", "abdomen", "nhdr", KLACANSKY + "pancreas/pancreas.nhdr",
            "CT abdominal con contraste, int16 240x512x512 (NIH Pancreas-CT)",
            "klacansky / NIH Clinical Center", "CC BY 3.0 (Pancreas-CT)", ("raw",),
            extra_urls=(KLACANSKY + "pancreas/pancreas_240x512x512_int16.raw",)),
    Dataset("klacansky_vis_male", "cabeza", "nhdr", KLACANSKY + "vis_male/vis_male.nhdr",
            "Cabeza del Visible Male, uint8 128x256x256", "klacansky / NLM",
            "ver open-scivis-datasets", ("raw",), hu_offset=None,
            extra_urls=(KLACANSKY + "vis_male/vis_male_128x256x256_uint8.raw",)),
    # --- PVM (open-terrain) ---------------------------------------------------------------------
    Dataset("ot_ct_head", "cabeza", "pvm", OPEN_TERRAIN + "CT-Head.pvm",
            "Chapel Hill CT Head (cadaver), 16 bit 256x256x113", "open-terrain / Stanford (Levoy)",
            "uso no comercial", ("pvm",), hu_offset=None),
    Dataset("ot_cadaver", "cabeza", "pvm", OPEN_TERRAIN + "Cadaver.pvm",
            "Cabeza de cadaver (artefactos dentales), 16 bit 512x512x106", "open-terrain / Erlangen",
            "uso no comercial", ("pvm",), hu_offset=None),
    Dataset("ot_ct_chest", "torax", "pvm", OPEN_TERRAIN + "CT-Chest.pvm",
            "Torax femenino, 8 bit 384x384x240", "open-terrain / University of Iowa",
            "uso no comercial", ("pvm",), hu_offset=None),
    Dataset("ot_ct_abdomen", "abdomen", "pvm", OPEN_TERRAIN + "CT-Abdomen.pvm",
            "CT de abdomen, 8 bit 512x512x147", "open-terrain / Ohm University", "uso no comercial",
            ("pvm",), hu_offset=None),
]


def by_id(dataset_id: str) -> Dataset:
    for d in CATALOG:
        if d.id == dataset_id:
            return d
    raise KeyError(dataset_id)


# --------------------------------------------------------------------------------------------
# Descarga
# --------------------------------------------------------------------------------------------

def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "axial-tools"})
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    tmp.replace(dest)
    return dest


# --------------------------------------------------------------------------------------------
# NRRD / NHDR (lector propio)
# --------------------------------------------------------------------------------------------

NRRD_TYPES = {
    "uchar": "u1", "unsigned char": "u1", "uint8": "u1", "uint8_t": "u1",
    "signed char": "i1", "int8": "i1", "int8_t": "i1",
    "short": "i2", "short int": "i2", "signed short": "i2", "int16": "i2", "int16_t": "i2",
    "ushort": "u2", "unsigned short": "u2", "uint16": "u2", "uint16_t": "u2",
    "int": "i4", "signed int": "i4", "int32": "i4", "int32_t": "i4",
    "uint": "u4", "unsigned int": "u4", "uint32": "u4", "uint32_t": "u4",
    "float": "f4", "double": "f8",
}


def read_nrrd(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (datos (i,j,k), afin voxel -> RAS)."""
    raw = Path(path).read_bytes()
    head_end = raw.find(b"\n\n")
    header = raw[: head_end if head_end >= 0 else len(raw)].decode("latin-1")
    fields: dict[str, str] = {}
    for line in header.splitlines()[1:]:
        if line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip().lstrip("=").strip()

    sizes = [int(v) for v in fields["sizes"].split()]
    if len(sizes) != 3:
        raise ValueError(f"solo NRRD 3D: sizes={sizes}")
    dtype = np.dtype(NRRD_TYPES[fields["type"].lower()])
    if dtype.itemsize > 1:
        dtype = dtype.newbyteorder("<" if fields.get("endian", "little") == "little" else ">")
    encoding = fields.get("encoding", "raw").lower()

    if "data file" in fields or "datafile" in fields:
        payload = (Path(path).parent / (fields.get("data file") or fields["datafile"])).read_bytes()
    else:
        payload = raw[head_end + 2:]
    if encoding in ("gzip", "gz"):
        payload = gzip.decompress(payload)
    elif encoding != "raw":
        raise ValueError(f"encoding NRRD no soportado: {encoding}")

    n = int(np.prod(sizes))
    if len(payload) < n * dtype.itemsize:
        raise ValueError(f"NRRD truncado: {len(payload)} bytes, se esperaban {n * dtype.itemsize}")
    data = np.frombuffer(payload, dtype=dtype, count=n).reshape(sizes[::-1]).transpose(2, 1, 0)

    affine = np.eye(4)
    if "space directions" in fields:
        vecs = re.findall(r"\(([^)]*)\)", fields["space directions"])
        for a, v in enumerate(vecs[:3]):
            affine[:3, a] = [float(x) for x in v.split(",")]
    elif "spacings" in fields:
        affine[:3, :3] = np.diag([float(x) for x in fields["spacings"].split()])
    if "space origin" in fields:
        affine[:3, 3] = [float(x) for x in re.findall(r"[-+0-9.eE]+", fields["space origin"])[:3]]
    space = fields.get("space", "").lower()
    if space in ("left-posterior-superior", "lps"):
        affine = LPS_TO_RAS @ affine
    elif space not in ("right-anterior-superior", "ras", ""):
        raise ValueError(f"espacio NRRD no soportado: {space}")
    return np.ascontiguousarray(data), affine


# --------------------------------------------------------------------------------------------
# PVM con compresion DDS (lector propio)
# --------------------------------------------------------------------------------------------

def dds_decode(chunk: bytes, interleave_block: int) -> bytes:
    """Decodifica un flujo DDS (v3d: interleave_block = 0; v3e: 1 << 24).

    El flujo son palabras de 32 bits big-endian, leidas desde el bit mas significativo:
    skip (2 bits) + strip (16 bits), luego bloques [n (7 bits), bits (3 bits)] con n deltas de
    `bits` bits; cada valor es el anterior + delta (o, con strip, la prediccion por la fila
    previa) modulo 256. Al final se re-intercala con paso `skip`.
    """
    words = np.frombuffer(chunk + b"\0" * (-len(chunk) % 4), dtype=">u4").tolist()
    nwords = len(words)
    pos = 0
    buf = 0
    bufsize = 0

    def readbits(bits: int) -> int:
        nonlocal pos, buf, bufsize
        if bits < bufsize:
            bufsize -= bits
            value = buf >> bufsize
        else:
            value = (buf << (bits - bufsize)) & 0xFFFFFFFF if bits - bufsize < 32 else 0
            if pos < nwords:
                buf = words[pos]
                pos += 1
            else:
                buf = 0
            bufsize += 32 - bits
            value |= buf >> bufsize if bufsize < 32 else 0
        buf &= (1 << bufsize) - 1
        return value

    skip = readbits(2) + 1
    strip = readbits(16) + 1
    out = bytearray()
    act = 0
    cnt = 0
    while True:
        n = readbits(7)
        if n == 0:
            break
        code = readbits(3)
        bits = code + 1 if code >= 1 else code
        half = (1 << bits) // 2
        for _ in range(n):
            if strip == 1 or cnt <= strip:
                act += readbits(bits) - half
            else:
                act += out[cnt - strip] - out[cnt - strip - 1] + readbits(bits) - half
            act &= 0xFF
            out.append(act)
            cnt += 1
    return bytes(_dds_interleave(np.frombuffer(bytes(out), np.uint8), skip, interleave_block))


def _dds_interleave(data: np.ndarray, skip: int, block: int) -> np.ndarray:
    """Inverso del des-intercalado: los bytes j, j+skip, j+2skip... estaban agrupados."""
    if skip <= 1 or len(data) == 0:
        return data
    out = np.empty_like(data)
    chunk = len(data) if block == 0 else skip * block
    for start in range(0, len(data), chunk):
        part = data[start:start + chunk]
        m = len(part)
        dst = out[start:start + m]
        ptr = 0
        for i in range(skip):
            cnt = len(range(i, m, skip))
            dst[i::skip] = part[ptr:ptr + cnt]
            ptr += cnt
    return out


def read_pvm(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    raw = Path(path).read_bytes()
    if raw.startswith(b"DDS v3d\n"):
        data = dds_decode(raw[8:], 0)
    elif raw.startswith(b"DDS v3e\n"):
        data = dds_decode(raw[8:], 1 << 24)
    else:
        data = raw
    spacing = (1.0, 1.0, 1.0)
    if data.startswith(b"PVM\n"):
        rest = data[4:]
        while rest.startswith(b"#"):
            rest = rest[rest.index(b"\n") + 1:]
        line, rest = rest.split(b"\n", 1)
        dims = [int(v) for v in line.split()]
    elif data[:5] in (b"PVM2\n", b"PVM3\n"):
        line, rest = data[5:].split(b"\n", 1)
        dims = [int(v) for v in line.split()]
        line, rest = rest.split(b"\n", 1)
        spacing = tuple(float(v) for v in line.split())
    else:
        raise ValueError("no es un PVM")
    line, rest = rest.split(b"\n", 1)
    comps = int(line)
    n = int(np.prod(dims))
    voxels = np.frombuffer(rest[: n * comps], dtype=np.uint8 if comps == 1 else ">u2")
    if comps not in (1, 2):
        raise ValueError(f"PVM con {comps} componentes (RGB?) no soportado")
    vol = voxels.reshape(dims[::-1]).transpose(2, 1, 0)
    texts = rest[n * comps:].split(b"\0")
    meta = {"descripcion": texts[0].decode("latin-1", "replace") if texts else "",
            "bytes_por_voxel": comps}
    # PVM no guarda orientacion: se asume i -> R, j -> A, k -> S (se documenta)
    return np.ascontiguousarray(vol), np.diag([*spacing, 1.0]), meta


# --------------------------------------------------------------------------------------------
# Conversion + niveles de detalle
# --------------------------------------------------------------------------------------------

def resample_isotropic(data: np.ndarray, affine: np.ndarray, spacing_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """Remuestreo trilineal a voxel isotropico, conservando la orientacion de los ejes."""
    current = np.linalg.norm(affine[:3, :3], axis=0)
    zoom = current / spacing_mm
    out = ndimage.zoom(data.astype(np.float32), zoom, order=1, mode="nearest", grid_mode=True)
    new_affine = affine.copy()
    new_affine[:3, :3] = affine[:3, :3] / current * spacing_mm
    # el centro del primer voxel se corre medio voxel nuevo respecto del viejo
    shift = (spacing_mm - current) / 2
    new_affine[:3, 3] = affine[:3, 3] + affine[:3, :3] @ (shift / current)
    return out, new_affine


def save_nifti(path: Path, data: np.ndarray, affine: np.ndarray) -> None:
    if np.issubdtype(data.dtype, np.floating) and np.all(np.isfinite(data)) \
            and data.min() >= -32768 and data.max() <= 32767:
        data = np.rint(data).astype(np.int16)
    img = nib.Nifti1Image(data, affine)
    img.header.set_xyzt_units("mm")
    img.header.set_qform(affine, code=1)
    img.header.set_sform(affine, code=1)
    nib.save(img, str(path))


@dataclass
class Converted:
    id: str
    region: str
    file: str
    dims: list[int]
    spacing_mm: list[float]
    axcodes: str
    value_min: float
    value_max: float
    in_hu: bool
    voxels: int
    source_format: str
    license: str
    lods: dict[str, dict] = field(default_factory=dict)
    notes: str = ""


def load_native(ds: Dataset, cache: Path) -> tuple[np.ndarray, np.ndarray, str]:
    """Descarga (con cache) y lee el dataset en su formato. Devuelve (datos, afin RAS, notas)."""
    folder = cache / ds.id
    if ds.kind == "nifti":
        f = download(ds.url, folder / "original.nii.gz")
        img = nib.load(str(f))
        return np.asarray(img.dataobj), img.affine, ""
    if ds.kind in ("nrrd", "nhdr"):
        name = Path(ds.url).name if ds.kind == "nhdr" else "original.nrrd"
        f = download(ds.url, folder / name)
        for extra in ds.extra_urls:
            download(extra, folder / Path(extra).name)
        data, affine = read_nrrd(f)
        return data, affine, ""
    if ds.kind == "pvm":
        f = download(ds.url, folder / Path(ds.url).name)
        data, affine, meta = read_pvm(f)
        return data, affine, f"PVM sin orientacion (se asume RAS); {meta['descripcion']}"
    if ds.kind == "dicom":
        dcm_dir = folder / "dicom"
        if not dcm_dir.exists() or not any(dcm_dir.glob("*.dcm")):
            z = download(ds.url, folder / "serie.zip")
            with zipfile.ZipFile(z) as zf:
                dcm_dir.mkdir(parents=True, exist_ok=True)
                for member in zf.infolist():
                    if member.filename.lower().endswith(".dcm"):
                        target = dcm_dir / Path(member.filename).name
                        target.write_bytes(zf.read(member))
        vol = read_dicom_series(dcm_dir)
        return vol.data, vol.affine, f"serie DICOM en {dcm_dir}"
    if ds.kind == "dicom_from":
        dcm_dir = folder / "dicom"
        source = by_id(ds.url)
        data, affine, _ = load_native(source, cache)
        if not dcm_dir.exists() or not any(dcm_dir.glob("*.dcm")):
            write_axial_dicom(dcm_dir, data, affine)
        vol = read_dicom_series(dcm_dir)
        return vol.data, vol.affine, f"serie DICOM derivada de {ds.url} en {dcm_dir}"
    raise ValueError(ds.kind)


def write_axial_dicom(folder: Path, data: np.ndarray, affine: np.ndarray) -> None:
    """Escribe un volumen (HU) como serie DICOM axial estandar (IOP 1,0,0,0,1,0)."""
    from pydicom.uid import generate_uid

    from axial_tools.phantoms import _ct_slice

    img = nib.as_closest_canonical(nib.Nifti1Image(np.asarray(data), affine))  # i->R, j->A, k->S
    vol = np.asarray(img.dataobj).astype(np.float32)
    aff = img.affine
    ni, nj, nk = vol.shape
    sx, sy, sz = (float(v) for v in np.linalg.norm(aff[:3, :3], axis=0))
    folder.mkdir(parents=True, exist_ok=True)
    study, series, frame = generate_uid(), generate_uid(), generate_uid()
    for k in range(nk):
        # fila r crece hacia P (j decreciente), columna c hacia L (i decreciente)
        pixels = vol[::-1, ::-1, k].T
        ras = aff[:3, :3] @ np.array([ni - 1, nj - 1, k], float) + aff[:3, 3]
        ipp = [-ras[0], -ras[1], ras[2]]
        _ct_slice(folder / f"IM{k + 1:04d}.dcm", pixels, study_uid=study, series_uid=series,
                  frame_uid=frame, instance=k + 1, ipp=ipp, iop=[1, 0, 0, 0, 1, 0],
                  pixel_spacing=(sy, sx), thickness=sz)


def convert(ds: Dataset, cache: Path, out: Path, lods: bool) -> Converted:
    data, affine, notes = load_native(ds, cache)
    if ds.hu_offset is not None:
        data = data.astype(np.float32) + ds.hu_offset
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{ds.id}.nii.gz"
    save_nifti(path, data, affine)
    img = nib.load(str(path))
    arr = np.asarray(img.dataobj)
    conv = Converted(
        id=ds.id, region=ds.region, file=path.name, dims=list(arr.shape),
        spacing_mm=[round(float(s), 5) for s in img.header.get_zooms()[:3]],
        axcodes="".join(nib.aff2axcodes(img.affine)), value_min=float(arr.min()),
        value_max=float(arr.max()), in_hu=ds.hu_offset is not None, voxels=int(arr.size),
        source_format=ds.kind, license=ds.license, notes=notes)
    if lods:
        for name, mm in (("preview", 4.0), ("full", 1.0)):
            res, aff = resample_isotropic(arr, img.affine, mm)
            lod_path = out / f"{ds.id}__{name}.nii.gz"
            save_nifti(lod_path, res, aff)
            conv.lods[name] = {"file": lod_path.name, "dims": list(res.shape), "voxels": int(res.size)}
    return conv


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("fetch")
    f.add_argument("--out", type=Path, default=Path("out/datasets"))
    f.add_argument("--cache", type=Path, default=Path("out/datasets_cache"))
    f.add_argument("--only", default="", help="ids separados por coma")
    f.add_argument("--role", default="", help="solo los que tengan este rol (ej. medicion)")
    f.add_argument("--lods", action="store_true", help="generar preview (4 mm) y full (1 mm)")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for d in CATALOG:
            print(f"{d.id:22} {d.region:8} {d.kind:6} {','.join(d.roles):28} {d.license:28} {d.description}")
        return

    wanted = [d for d in CATALOG
              if (not args.only or d.id in args.only.split(","))
              and (not args.role or args.role in d.roles)]
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for d in wanted:
        print(f"{d.id} ...", end="", flush=True)
        try:
            conv = convert(d, args.cache, args.out, args.lods)
        except Exception as exc:  # noqa: BLE001 (se reporta y se sigue con el resto)
            print(f" ERROR: {exc}")
            continue
        manifest[d.id] = asdict(conv)
        print(f" {conv.dims} {conv.spacing_mm} mm {conv.axcodes} [{conv.value_min:.0f}, {conv.value_max:.0f}]"
              + (f" lods={ {k: v['dims'] for k, v in conv.lods.items()} }" if conv.lods else ""))
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


__all__ = ["CATALOG", "Dataset", "dds_decode", "read_nrrd", "read_pvm", "resample_isotropic"]
