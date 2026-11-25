"""Volumenes sinteticos ("fantasmas") con geometria conocida en mm (plan de implementacion, C).

Todas las formas se definen en coordenadas del mundo RAS+ en mm (x -> Right, y -> Anterior,
z -> Superior, la convencion de NIfTI/nibabel) y se rasterizan sobre cualquier grilla. Asi el
mismo objeto se escribe como NIfTI (con distintas orientaciones de almacenamiento), como serie
DICOM (axial, sagital, con defectos) y como RAW, y todas las versiones deben verse identicas.

Uso:
    uv run axial-phantoms --out out/phantoms
    uv run axial-phantoms --out ../../volume-renderer-ts/public/phantoms --nifti-only

Los archivos generados no se versionan (van a carpetas ignoradas); este script si, para que
sean reproducibles. `manifest.json` describe cada archivo, para que caso de prueba sirve y que
resultado se espera.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, MRImageStorage, generate_uid

AIR_HU = -1000

# --------------------------------------------------------------------------------------------
# Formas
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Shape:
    """Una forma con valor constante. `kind`: sphere | box | cylinder_z | ellipsoid | ring_z."""

    kind: str
    center: tuple[float, float, float]
    value: float
    radius: float = 0.0
    size: tuple[float, float, float] = (0.0, 0.0, 0.0)  # box: lados; ellipsoid/ring: semiejes
    height: float = 0.0  # cylinder_z, ring_z: alto en z
    inner: float = 0.0  # ring_z: fraccion interna del semieje (0..1)
    label: str = ""


def _mask(shape: Shape, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    cx, cy, cz = shape.center
    dx, dy, dz = x - cx, y - cy, z - cz
    if shape.kind == "sphere":
        return dx * dx + dy * dy + dz * dz <= shape.radius**2
    if shape.kind == "box":
        hx, hy, hz = (s / 2 for s in shape.size)
        return (np.abs(dx) <= hx) & (np.abs(dy) <= hy) & (np.abs(dz) <= hz)
    if shape.kind == "cylinder_z":
        return (dx * dx + dy * dy <= shape.radius**2) & (np.abs(dz) <= shape.height / 2)
    if shape.kind == "ellipsoid":
        a, b, c = shape.size
        return (dx / a) ** 2 + (dy / b) ** 2 + (dz / c) ** 2 <= 1
    if shape.kind == "ring_z":
        a, b, _ = shape.size
        r2 = (dx / a) ** 2 + (dy / b) ** 2
        return (r2 <= 1) & (r2 >= shape.inner**2) & (np.abs(dz) <= shape.height / 2)
    raise ValueError(f"forma desconocida: {shape.kind}")


def evaluate(shapes: list[Shape], background: float, x, y, z) -> np.ndarray:
    """Valor en cada punto (arrays con broadcasting). Las formas posteriores pisan a las anteriores."""
    out = np.full(np.broadcast_shapes(np.shape(x), np.shape(y), np.shape(z)), background, np.float64)
    for s in shapes:
        out[np.broadcast_to(_mask(s, x, y, z), out.shape)] = s.value
    return out


# --------------------------------------------------------------------------------------------
# Grillas (NIfTI): afin RAS + dims. Solo afines que son permutaciones con signo (sin oblicuidad),
# asi cada coordenada del mundo depende de un solo eje de voxel y se evalua con broadcasting.
# --------------------------------------------------------------------------------------------


@dataclass
class Grid:
    dims: tuple[int, int, int]
    affine: np.ndarray  # 4x4, voxel (i,j,k) -> RAS mm


def centered_grid(dims: tuple[int, int, int], spacing: tuple[float, float, float],
                  axes: tuple[str, str, str] = ("R", "A", "S")) -> Grid:
    """Grilla centrada en el origen. `axes`: hacia donde crece cada eje de voxel (ej. LPS, PIR)."""
    world = {"R": (0, 1), "L": (0, -1), "A": (1, 1), "P": (1, -1), "S": (2, 1), "I": (2, -1)}
    affine = np.zeros((4, 4))
    affine[3, 3] = 1
    for a, letter in enumerate(axes):
        w, sign = world[letter]
        affine[w, a] = sign * spacing[a]
    center_index = (np.array(dims) - 1) / 2
    affine[:3, 3] = -affine[:3, :3] @ center_index
    return Grid(dims, affine)


def rasterize(shapes: list[Shape], background: float, grid: Grid) -> np.ndarray:
    ni, nj, nk = grid.dims
    idx = [np.arange(ni).reshape(-1, 1, 1), np.arange(nj).reshape(1, -1, 1),
           np.arange(nk).reshape(1, 1, -1)]
    coords = []
    for w in range(3):
        c = grid.affine[w, 3] + sum(grid.affine[w, a] * idx[a] for a in range(3) if grid.affine[w, a])
        coords.append(np.asarray(c, dtype=np.float64))
    return np.broadcast_to(evaluate(shapes, background, *coords), grid.dims).copy()


# --------------------------------------------------------------------------------------------
# Definicion de los fantasmas
# --------------------------------------------------------------------------------------------

GEOMETRIC = [
    Shape("sphere", (50.0, 0.0, 0.0), 1000, radius=40.0, label="esfera r=40 mm"),
    Shape("box", (-50.0, 0.0, 0.0), 400, size=(50.0, 50.0, 50.0), label="cubo lado 50 mm"),
]

MARKERS = [
    Shape("sphere", (0.0, 0.0, 0.0), 200, radius=8.0, label="centro"),
    Shape("sphere", (60.0, 0.0, 0.0), 800, radius=20.0, label="derecha (R)"),
    Shape("box", (0.0, 60.0, 0.0), 400, size=(30.0, 30.0, 30.0), label="anterior (A)"),
    Shape("cylinder_z", (0.0, 0.0, 60.0), 1500, radius=10.0, height=30.0, label="superior (S)"),
]


def torso_shapes() -> list[Shape]:
    """Torso esquematico (no anatomico): cuerpo, pulmones, corazon, columna y costillas."""
    shapes = [
        Shape("ellipsoid", (0, 0, 0), -80, size=(150, 100, 140), label="grasa subcutanea"),
        Shape("ellipsoid", (0, 0, 0), 40, size=(140, 92, 132), label="tejido blando"),
        Shape("ellipsoid", (60, 0, 20), -820, size=(45, 60, 90), label="pulmon derecho"),
        Shape("ellipsoid", (-60, 0, 20), -820, size=(45, 60, 90), label="pulmon izquierdo"),
        Shape("ellipsoid", (-20, 20, 0), 50, size=(45, 40, 45), label="corazon"),
        Shape("cylinder_z", (0, -70, 0), 700, radius=15, height=260, label="columna"),
    ]
    for z in (-60, -36, -12, 12, 36, 60):
        shapes.append(Shape("ring_z", (0, 0, z), 700, size=(138, 90, 0), height=8, inner=0.9,
                            label=f"costilla z={z}"))
    return shapes


# --------------------------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------------------------


@dataclass
class Entry:
    file: str
    kind: str
    purpose: str
    expected: dict = field(default_factory=dict)


def write_nifti(path: Path, data: np.ndarray, grid: Grid, dtype=np.int16,
                slope: float | None = None, inter: float | None = None) -> None:
    img = nib.Nifti1Image(data.astype(dtype), grid.affine)
    img.header.set_xyzt_units("mm")
    img.header.set_qform(grid.affine, code=1)
    img.header.set_sform(grid.affine, code=1)
    if slope is not None:
        img.header.set_slope_inter(slope, inter)
    nib.save(img, str(path))


def _ct_slice(path: Path, pixels: np.ndarray, *, study_uid: str, series_uid: str, frame_uid: str,
              instance: int, ipp, iop, pixel_spacing, thickness: float, modality: str = "CT",
              series_number: int = 1) -> None:
    sop_class = CTImageStorage if modality == "CT" else MRImageStorage
    sop_uid = generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = sop_uid
    ds.PatientName = "Fantasma^Axial"
    ds.PatientID = "FANTASMA"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.FrameOfReferenceUID = frame_uid
    ds.Modality = modality
    ds.SeriesNumber = series_number
    ds.InstanceNumber = instance
    ds.ImagePositionPatient = [f"{v:.4f}" for v in ipp]
    ds.ImageOrientationPatient = [f"{v:.6f}" for v in iop]
    ds.PixelSpacing = [f"{v:.4f}" for v in pixel_spacing]
    ds.SliceThickness = f"{thickness:.4f}"
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    # Almacenado sin signo con intercept -1024: obliga a aplicar RescaleSlope/Intercept.
    ds.RescaleIntercept = -1024
    ds.RescaleSlope = 1
    ds.RescaleType = "HU"
    stored = np.clip(np.rint(pixels + 1024), 0, 65535).astype("<u2")
    ds.PixelData = stored.tobytes()
    ds.save_as(str(path), enforce_file_format=True)


def write_dicom_series(folder: Path, shapes: list[Shape], *, rows: int, cols: int,
                       pixel_spacing: tuple[float, float], positions: list[np.ndarray],
                       row_dir, col_dir, thickness: float, modality: str = "CT",
                       series_uid: str | None = None, study_uid: str | None = None,
                       series_number: int = 1, prefix: str = "IM") -> None:
    """Serie DICOM. Direcciones y posiciones en LPS (convencion DICOM), en mm.

    row_dir: direccion en que crece el indice de COLUMNA dentro de una fila (IOP[0:3]);
    col_dir: direccion en que crece el indice de FILA (IOP[3:6]);
    pixel_spacing = (separacion entre filas, separacion entre columnas).
    """
    folder.mkdir(parents=True, exist_ok=True)
    study_uid = study_uid or generate_uid()
    series_uid = series_uid or generate_uid()
    frame_uid = generate_uid()
    row_dir = np.asarray(row_dir, float)
    col_dir = np.asarray(col_dir, float)
    r = np.arange(rows).reshape(-1, 1)
    c = np.arange(cols).reshape(1, -1)
    for n, ipp in enumerate(positions):
        lps = [ipp[d] + c * pixel_spacing[1] * row_dir[d] + r * pixel_spacing[0] * col_dir[d]
               for d in range(3)]
        # LPS -> RAS
        hu = evaluate(shapes, AIR_HU, -lps[0], -lps[1], lps[2])
        hu = np.broadcast_to(hu, (rows, cols))
        _ct_slice(folder / f"{prefix}{n + 1:04d}.dcm", hu, study_uid=study_uid, series_uid=series_uid,
                  frame_uid=frame_uid, instance=n + 1, ipp=ipp, iop=[*row_dir, *col_dir],
                  pixel_spacing=pixel_spacing, thickness=thickness, modality=modality,
                  series_number=series_number)


def axial_positions(n: int, spacing: float, rows: int, cols: int,
                    pixel_spacing: tuple[float, float]) -> list[np.ndarray]:
    """Cortes axiales centrados en el origen: filas hacia P, columnas hacia L (IOP 1,0,0,0,1,0)."""
    x0 = -(cols - 1) / 2 * pixel_spacing[1]
    y0 = -(rows - 1) / 2 * pixel_spacing[0]
    z0 = -(n - 1) / 2 * spacing
    return [np.array([x0, y0, z0 + k * spacing]) for k in range(n)]


def gzip_bytes(path: Path, data: bytes) -> None:
    with gzip.open(path, "wb") as f:
        f.write(data)


# --------------------------------------------------------------------------------------------
# Generacion
# --------------------------------------------------------------------------------------------


def _shapes_json(shapes: list[Shape]) -> list[dict]:
    return [{k: v for k, v in asdict(s).items() if v not in (0.0, (0.0, 0.0, 0.0), "")} | {"kind": s.kind}
            for s in shapes]


def generate(out: Path, nifti_only: bool = False, with_torso_full: bool = True) -> list[Entry]:
    out.mkdir(parents=True, exist_ok=True)
    entries: list[Entry] = []

    # --- geometrico anisotropico (CP-F01, CP-F04, CP-F07, CP-R01) ---------------------------
    geo_spacing = (0.7, 0.7, 2.5)
    geo_grid = centered_grid((286, 286, 80), geo_spacing)
    geo = rasterize(GEOMETRIC, AIR_HU, geo_grid)
    write_nifti(out / "geometrico_aniso.nii.gz", geo, geo_grid)
    entries.append(Entry("geometrico_aniso.nii.gz", "nifti", "CP-F01, CP-R01", {
        "dims": list(geo_grid.dims), "spacing_mm": list(geo_spacing), "axcodes": "RAS",
        "shapes": _shapes_json(GEOMETRIC),
        "cp_r01": "esfera: diametro aparente 80 mm; cubo: lado aparente 50 mm (camara ortografica)",
    }))

    # --- marcadores asimetricos en 3 orientaciones de almacenamiento (CP-F10, CP-R02) ----------
    mk_spacing = (1.0, 1.0, 2.0)
    for axes, name in ((("R", "A", "S"), "marcadores_ras"), (("L", "P", "S"), "marcadores_lps")):
        grid = centered_grid((200, 200, 100), mk_spacing, axes)
        write_nifti(out / f"{name}.nii.gz", rasterize(MARKERS, AIR_HU, grid), grid)
        entries.append(Entry(f"{name}.nii.gz", "nifti", "CP-F10, CP-R02", {
            "axcodes": "".join(axes), "markers": _shapes_json(MARKERS),
            "cp_r02": "derecha del paciente a la izquierda del observador (vista anterior); "
                      "anterior hacia la camara inicial; superior arriba",
        }))
    # adquisicion "sagital": i -> P, j -> I, k -> R
    grid = centered_grid((200, 100, 200), (1.0, 2.0, 1.0), ("P", "I", "R"))
    write_nifti(out / "marcadores_sagital.nii.gz", rasterize(MARKERS, AIR_HU, grid), grid)
    entries.append(Entry("marcadores_sagital.nii.gz", "nifti", "CP-F06 (NIfTI), CP-R02", {
        "axcodes": "PIR", "markers": _shapes_json(MARKERS),
        "nota": "debe verse identico a marcadores_ras y marcadores_lps",
    }))

    # --- NIfTI con scl_slope/scl_inter (CP-F03) ------------------------------------------------
    stored = (geo + 1024) / 2  # HU = 2 * stored - 1024 (exacto: todos los HU son pares)
    write_nifti(out / "nifti_scl.nii.gz", stored, geo_grid, slope=2.0, inter=-1024.0)
    entries.append(Entry("nifti_scl.nii.gz", "nifti", "CP-F03", {
        "scl_slope": 2.0, "scl_inter": -1024.0, "hu_values": [AIR_HU, 400, 1000],
    }))

    # --- NIfTI danados (CP-F02) -------------------------------------------------------------------
    small_grid = centered_grid((64, 64, 32), (2.0, 2.0, 4.0))
    write_nifti(out / "_tmp_ok.nii", rasterize(MARKERS, AIR_HU, small_grid), small_grid)
    raw_bytes = (out / "_tmp_ok.nii").read_bytes()
    (out / "_tmp_ok.nii").unlink()
    bad_magic = bytearray(raw_bytes)
    bad_magic[344:348] = b"xxxx"
    (out / "nifti_cabecera_danada.nii").write_bytes(bytes(bad_magic))
    gzip_bytes(out / "nifti_truncado.nii.gz", raw_bytes[: int(len(raw_bytes) * 0.7)])
    entries.append(Entry("nifti_cabecera_danada.nii", "nifti", "CP-F02", {"esperado": "rechazo: firma invalida"}))
    entries.append(Entry("nifti_truncado.nii.gz", "nifti", "CP-F02",
                         {"esperado": "rechazo: tamano inconsistente con la cabecera"}))

    # --- torso sintetico (pruebas del arnes de FPS/SSIM sin datos reales) ------------------------
    torso = torso_shapes()
    sizes = {"torso_preview": 4.0}
    if with_torso_full:
        sizes["torso_full"] = 1.0
    for name, sp in sizes.items():
        dims = tuple(round(extent / sp) for extent in (330, 240, 300))
        grid = centered_grid(dims, (sp, sp, sp))
        write_nifti(out / f"{name}.nii.gz", rasterize(torso, AIR_HU, grid), grid)
        entries.append(Entry(f"{name}.nii.gz", "nifti", "arnes (B): FPS, carga, SSIM", {
            "dims": list(dims), "spacing_mm": [sp] * 3, "voxels": int(np.prod(dims)),
            "nota": "esquematico, no anatomico: solo para probar la canalizacion de medicion",
        }))

    if not nifti_only:
        entries += _generate_dicom(out)
        entries += _generate_raw(out, geo, geo_grid)

    (out / "manifest.json").write_text(json.dumps([asdict(e) for e in entries], indent=2,
                                                  ensure_ascii=False), encoding="utf-8")
    return entries


def _generate_dicom(out: Path) -> list[Entry]:
    entries: list[Entry] = []
    d = out / "dicom"
    if d.exists():
        shutil.rmtree(d)

    # Geometrico anisotropico axial (CP-F04)
    ps = (0.7, 0.7)
    rows = cols = 286
    pos = axial_positions(80, 2.5, rows, cols, ps)
    write_dicom_series(d / "geometrico_axial", GEOMETRIC, rows=rows, cols=cols, pixel_spacing=ps,
                       positions=pos, row_dir=(1, 0, 0), col_dir=(0, 1, 0), thickness=2.5)
    entries.append(Entry("dicom/geometrico_axial", "dicom", "CP-F04", {
        "cortes": 80, "pixel_spacing": list(ps), "separacion": 2.5, "rescale_intercept": -1024}))

    # Marcadores axial y sagital (CP-F06, CP-F10)
    ps = (1.0, 1.0)
    rows = cols = 200
    pos = axial_positions(100, 2.0, rows, cols, ps)
    write_dicom_series(d / "marcadores_axial", MARKERS, rows=rows, cols=cols, pixel_spacing=ps,
                       positions=pos, row_dir=(1, 0, 0), col_dir=(0, 1, 0), thickness=2.0)
    entries.append(Entry("dicom/marcadores_axial", "dicom", "CP-F10", {"markers": _shapes_json(MARKERS)}))

    # Sagital: filas a lo largo de +y LPS (posterior), columnas hacia -z (inferior); los cortes
    # avanzan a lo largo de la normal row x col = (-1, 0, 0) LPS = hacia la derecha.
    srows, scols, n = 100, 200, 200
    sps = (2.0, 1.0)
    row_dir, col_dir = np.array([0, 1, 0]), np.array([0, 0, -1])
    normal = np.cross(row_dir, col_dir)
    first = np.array([0.0, -(scols - 1) / 2 * sps[1], (srows - 1) / 2 * sps[0]])
    first = first - normal * (n - 1) / 2 * 1.0
    positions = [first + normal * k * 1.0 for k in range(n)]
    write_dicom_series(d / "marcadores_sagital", MARKERS, rows=srows, cols=scols, pixel_spacing=sps,
                       positions=positions, row_dir=row_dir, col_dir=col_dir, thickness=1.0)
    entries.append(Entry("dicom/marcadores_sagital", "dicom", "CP-F06", {
        "iop": [*row_dir.tolist(), *col_dir.tolist()],
        "esperado": "reorientado a la convencion unica, marcadores en las mismas posiciones que el axial"}))

    # Defectos (CP-F05 y validacion de serie)
    small_ps = (2.0, 2.0)
    srows = scols = 100
    pos = axial_positions(40, 4.0, srows, scols, small_ps)
    write_dicom_series(d / "corte_faltante", MARKERS, rows=srows, cols=scols, pixel_spacing=small_ps,
                       positions=pos[:20] + pos[21:], row_dir=(1, 0, 0), col_dir=(0, 1, 0), thickness=4.0)
    entries.append(Entry("dicom/corte_faltante", "dicom", "CP-F05", {"falta": "corte 21 de 40 (salto 8 mm)"}))

    shifted = pos[:20] + [p + np.array([0, 0, 2.0]) for p in pos[20:]]
    write_dicom_series(d / "espaciado_no_uniforme", MARKERS, rows=srows, cols=scols,
                       pixel_spacing=small_ps, positions=shifted, row_dir=(1, 0, 0), col_dir=(0, 1, 0),
                       thickness=4.0)
    entries.append(Entry("dicom/espaciado_no_uniforme", "dicom", "CP-F05", {"salto": "6 mm entre cortes 20 y 21 (resto 4 mm)"}))

    write_dicom_series(d / "cortes_duplicados", MARKERS, rows=srows, cols=scols, pixel_spacing=small_ps,
                       positions=pos[:20] + [pos[19]] + pos[20:], row_dir=(1, 0, 0), col_dir=(0, 1, 0),
                       thickness=4.0)
    entries.append(Entry("dicom/cortes_duplicados", "dicom", "validacion de serie", {"duplicado": "corte 20"}))

    study = generate_uid()
    write_dicom_series(d / "mezcla_series", MARKERS, rows=srows, cols=scols, pixel_spacing=small_ps,
                       positions=pos, row_dir=(1, 0, 0), col_dir=(0, 1, 0), thickness=4.0,
                       study_uid=study, series_number=1, prefix="A")
    write_dicom_series(d / "mezcla_series", GEOMETRIC, rows=srows, cols=scols, pixel_spacing=small_ps,
                       positions=pos[:10], row_dir=(1, 0, 0), col_dir=(0, 1, 0), thickness=4.0,
                       study_uid=study, series_number=2, prefix="B")
    entries.append(Entry("dicom/mezcla_series", "dicom", "validacion de serie",
                         {"series": {"1": 40, "2": 10}, "esperado": "rechazo listando las series"}))

    write_dicom_series(d / "no_ct", MARKERS, rows=srows, cols=scols, pixel_spacing=small_ps,
                       positions=pos[:10], row_dir=(1, 0, 0), col_dir=(0, 1, 0), thickness=4.0,
                       modality="MR")
    entries.append(Entry("dicom/no_ct", "dicom", "validacion de serie", {"esperado": "rechazo: Modality MR"}))
    return entries


def _generate_raw(out: Path, geo: np.ndarray, grid: Grid) -> list[Entry]:
    """RAW: array (z, y, x) en orden C (x mas rapido), x = eje i del NIfTI geometrico (i -> R)."""
    entries: list[Entry] = []
    zyx = np.ascontiguousarray(np.transpose(geo, (2, 1, 0))).astype("<i2")
    nz, ny, nx = zyx.shape
    params = {"dims_zyx": [nz, ny, nx], "dtype": "int16", "spacing_zyx_mm": [2.5, 0.7, 0.7],
              "value_range_hu": [AIR_HU, 1000]}

    (out / "raw_geometrico_int16_le.raw").write_bytes(zyx.tobytes())
    entries.append(Entry("raw_geometrico_int16_le.raw", "raw", "CP-F07",
                         params | {"byte_order": "little", "esperado": "identico a geometrico_aniso.nii.gz"}))

    (out / "raw_tamano_incorrecto.raw").write_bytes(zyx.tobytes()[: -(nx * ny * 2) + 3])
    entries.append(Entry("raw_tamano_incorrecto.raw", "raw", "CP-F08",
                         params | {"byte_order": "little", "esperado": "rechazo: tamano no coincide (falta un corte, sobran 3 bytes)"}))

    (out / "raw_int16_big_endian.raw").write_bytes(zyx.astype(">i2").tobytes())
    entries.append(Entry("raw_int16_big_endian.raw", "raw", "CP-F09",
                         params | {"byte_order_real": "big", "byte_order_declarado": "little",
                                   "esperado": "advertencia de rango sospechoso"}))
    return entries


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("out/phantoms"))
    parser.add_argument("--nifti-only", action="store_true", help="solo NIfTI (para el frontend)")
    parser.add_argument("--no-torso-full", action="store_true", help="omitir el torso de 1 mm (~24 M voxeles)")
    args = parser.parse_args(argv)
    entries = generate(args.out, nifti_only=args.nifti_only, with_torso_full=not args.no_torso_full)
    for e in entries:
        print(f"{e.purpose:28s} {e.file}")
    print(f"{len(entries)} archivos en {args.out.resolve()}")


if __name__ == "__main__":
    main()
