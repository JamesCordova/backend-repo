"""Lecturas de referencia INDEPENDIENTES de la canalizacion (plan, C).

nibabel para NIfTI, pydicom (ordenando por ImagePositionPatient proyectada sobre la normal)
para DICOM y numpy para RAW. Nunca SimpleITK: no se usa al sistema como referencia de si mismo.
Todas devuelven el volumen en HU/valor real y una afin voxel -> RAS mm.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom

LPS_TO_RAS = np.diag([-1.0, -1.0, 1.0, 1.0])


@dataclass
class RefVolume:
    data: np.ndarray  # indices (i, j, k)
    affine: np.ndarray  # voxel -> RAS mm

    @property
    def spacing(self) -> np.ndarray:
        return np.linalg.norm(self.affine[:3, :3], axis=0)

    @property
    def axcodes(self) -> str:
        return "".join(nib.aff2axcodes(self.affine))

    def world_of(self, ijk) -> np.ndarray:
        return self.affine[:3, :3] @ np.asarray(ijk, float) + self.affine[:3, 3]


def read_nifti(path: Path) -> RefVolume:
    img = nib.load(str(path))
    return RefVolume(np.asarray(img.get_fdata(dtype=np.float64)), img.affine.copy())


def read_dicom_series(folder: Path) -> RefVolume:
    """Apila una serie (una sola) ordenada por la posicion proyectada sobre la normal."""
    datasets = [pydicom.dcmread(str(p)) for p in sorted(Path(folder).glob("*.dcm"))]
    if not datasets:
        raise ValueError(f"sin archivos DICOM en {folder}")
    series = {ds.SeriesInstanceUID for ds in datasets}
    if len(series) != 1:
        raise ValueError(f"{len(series)} series en {folder}")
    iop = np.array(datasets[0].ImageOrientationPatient, float)
    row_dir, col_dir = iop[:3], iop[3:]
    normal = np.cross(row_dir, col_dir)
    datasets.sort(key=lambda ds: float(np.dot(np.array(ds.ImagePositionPatient, float), normal)))
    positions = np.array([np.dot(np.array(ds.ImagePositionPatient, float), normal) for ds in datasets])
    gaps = np.diff(positions)
    slice_spacing = float(np.median(gaps)) if len(gaps) else 1.0

    slices = []
    for ds in datasets:
        arr = ds.pixel_array.astype(np.float64)
        slices.append(arr * float(ds.get("RescaleSlope", 1)) + float(ds.get("RescaleIntercept", 0)))
    # (k, filas, columnas) -> (i=columna, j=fila, k=corte)
    stack = np.transpose(np.stack(slices), (2, 1, 0))

    dr, dc = (float(v) for v in datasets[0].PixelSpacing)
    affine_lps = np.eye(4)
    affine_lps[:3, 0] = row_dir * dc
    affine_lps[:3, 1] = col_dir * dr
    affine_lps[:3, 2] = normal * slice_spacing
    affine_lps[:3, 3] = np.array(datasets[0].ImagePositionPatient, float)
    return RefVolume(stack, LPS_TO_RAS @ affine_lps)


def read_raw(path: Path, dims_zyx, dtype: str, spacing_zyx, byte_order: str = "little") -> RefVolume:
    """RAW (z, y, x) en orden C; sin orientacion: se asume i -> R, j -> A, k -> S."""
    dt = np.dtype(dtype).newbyteorder("<" if byte_order == "little" else ">")
    expected = int(np.prod(dims_zyx)) * dt.itemsize
    size = Path(path).stat().st_size
    if size != expected:
        raise ValueError(f"tamano {size} != {expected} bytes declarados")
    zyx = np.fromfile(str(path), dtype=dt).reshape(dims_zyx)
    sz, sy, sx = spacing_zyx
    return RefVolume(np.transpose(zyx, (2, 1, 0)).astype(np.float64), np.diag([sx, sy, sz, 1.0]))
