"""Genera una serie DICOM sintetica minima (unos pocos slices pequenos) para
pruebas, sin depender de descargar un dataset real de TCIA. Los valores de
RescaleSlope/RescaleIntercept/PixelSpacing/SliceThickness son conocidos de
antemano, para poder afirmar en los tests exactamente que HU y que spacing
se espera obtener -- una prueba de integracion contra un DICOM real (TCIA) es
un complemento a esto, no un reemplazo (ver seccion 18 del documento de
arquitectura), pendiente de agregar cuando se elija el dataset real.
"""

from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

RESCALE_SLOPE = 1.0
RESCALE_INTERCEPT = -1024.0
PIXEL_SPACING_MM = (0.5, 0.5)  # (row, col)
SLICE_THICKNESS_MM = 2.0


def write_synthetic_series(
    out_dir: Path, num_slices: int = 4, rows: int = 8, cols: int = 8
) -> list[Path]:
    """Escribe `num_slices` archivos .dcm en out_dir, todos parte de la misma
    serie, con pixeles crudos = indice de slice * 10 (para poder verificar el
    HU esperado tras aplicar rescale: hu = crudo*slope + intercept).
    """
    series_uid = generate_uid()
    study_uid = generate_uid()
    paths = []

    for i in range(num_slices):
        raw_value = i * 10
        pixel_array = np.full((rows, cols), raw_value, dtype=np.int16)

        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = CTImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.ImplementationClassUID = generate_uid()

        ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.PatientName = "Test^Sintetico"
        ds.PatientID = "TEST001"
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.SOPClassUID = CTImageStorage
        ds.Modality = "CT"
        ds.InstanceNumber = i + 1
        ds.ImagePositionPatient = [0.0, 0.0, float(i) * SLICE_THICKNESS_MM]
        ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        ds.PixelSpacing = list(PIXEL_SPACING_MM)
        ds.SliceThickness = SLICE_THICKNESS_MM
        ds.RescaleSlope = RESCALE_SLOPE
        ds.RescaleIntercept = RESCALE_INTERCEPT
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows = rows
        ds.Columns = cols
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1  # signed
        ds.PixelData = pixel_array.tobytes()

        path = out_dir / f"slice_{i:03d}.dcm"
        pydicom.dcmwrite(path, ds, little_endian=True, implicit_vr=False)
        paths.append(path)

    return paths


def write_oriented_series(
    out_dir: Path, iop: tuple[float, ...], first_position: tuple[float, float, float],
    num_slices: int, rows: int, cols: int, pixel_spacing: float, slice_step: float,
) -> list[Path]:
    """Serie con orientacion arbitraria donde cada pixel vale 10 * (coordenada S en mm,
    redondeada): permite verificar la reorientacion mirando solo los valores."""
    row_dir, col_dir = np.array(iop[:3], float), np.array(iop[3:], float)
    normal = np.cross(row_dir, col_dir)
    series_uid, study_uid = generate_uid(), generate_uid()
    r = np.arange(rows).reshape(-1, 1)
    c = np.arange(cols).reshape(1, -1)
    paths = []
    for k in range(num_slices):
        ipp = np.array(first_position, float) + normal * slice_step * k
        z = ipp[2] + c * pixel_spacing * row_dir[2] + r * pixel_spacing * col_dir[2]
        pixels = np.broadcast_to(np.rint(z * 10), (rows, cols)).astype(np.int16)

        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = CTImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, series_uid
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.SOPClassUID = CTImageStorage
        ds.Modality = "CT"
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(v) for v in ipp]
        ds.ImageOrientationPatient = [float(v) for v in iop]
        ds.PixelSpacing = [pixel_spacing, pixel_spacing]
        ds.SliceThickness = slice_step
        ds.RescaleSlope, ds.RescaleIntercept = 1.0, 0.0
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows, ds.Columns = rows, cols
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.PixelData = pixels.tobytes()
        path = out_dir / f"img_{k:03d}.dcm"
        pydicom.dcmwrite(path, ds, little_endian=True, implicit_vr=False)
        paths.append(path)
    return paths
