from pathlib import Path

import numpy as np
import pydicom
import SimpleITK as sitk

from processing.application.ports.volume_processor import VolumeProcessor
from processing.domain.entities import Volume


class SimpleItkVolumeProcessor(VolumeProcessor):
    def load_series(self, dicom_paths: list[Path]) -> Volume:
        # sitk.ImageSeriesReader aplica RescaleSlope/RescaleIntercept del DICOM
        # automaticamente -- el array resultante ya viene en Hounsfield units,
        # no en valores crudos de pixel.
        reader = sitk.ImageSeriesReader()
        # ImageSeriesReader apila los archivos en el orden recibido y toma el
        # spacing en z de los primeros: hay que ordenarlos por posicion. El
        # orden de subida/nombre de archivo no sirve (las exportaciones de TCIA,
        # por ejemplo, no estan en orden espacial: verificado con LIDC-IDRI).
        reader.SetFileNames([str(p) for p in _sort_by_position(dicom_paths)])
        image = reader.Execute()
        return _image_to_volume(image)

    def resample_to_isotropic(self, volume: Volume, target_spacing_mm: float) -> Volume:
        """Remuestreo isotropico y, en el MISMO Resample, reorientacion a la grilla
        canonica (plan E.2): direccion identidad en el espacio LPS de ITK (x -> L,
        y -> P, z -> S), cubriendo la caja fisica del volumen de entrada. Asi el
        frontend recibe siempre un volumen alineado a los ejes, se haya adquirido
        en axial, coronal, sagital u oblicuo (gantry tilt), sin interpretar la afin.
        Para una entrada ya canonica (RAW, DICOM axial estandar) el tamano es el
        mismo que antes: round(size * spacing / nuevo_spacing)."""
        image = volume_to_image(volume)
        size = np.array(image.GetSize())

        # Caja fisica de los BORDES de los voxeles (indices -0.5 y size - 0.5).
        corners = []
        for cx in (-0.5, size[0] - 0.5):
            for cy in (-0.5, size[1] - 0.5):
                for cz in (-0.5, size[2] - 0.5):
                    corners.append(image.TransformContinuousIndexToPhysicalPoint((cx, cy, cz)))
        corners = np.array(corners)
        low, high = corners.min(axis=0), corners.max(axis=0)

        new_spacing = (target_spacing_mm, target_spacing_mm, target_spacing_mm)
        new_size = [max(1, round(float(e) / target_spacing_mm)) for e in high - low]
        new_origin = tuple(float(v) for v in low + target_spacing_mm / 2)

        resampled = sitk.Resample(
            image,
            new_size,
            sitk.Transform(),
            sitk.sitkLinear,
            new_origin,
            new_spacing,
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            0.0,
            image.GetPixelID(),
        )
        return _image_to_volume(resampled)


def _sort_by_position(dicom_paths: list[Path]) -> list[Path]:
    """Ordena los cortes por ImagePositionPatient proyectada sobre la normal del
    plano (producto cruz de ImageOrientationPatient), leyendo solo la cabecera.
    Si a algun archivo le faltan esos tags se deja el orden recibido."""
    keys = []
    for path in dicom_paths:
        ds = pydicom.dcmread(str(path), stop_before_pixels=True)
        if "ImagePositionPatient" not in ds or "ImageOrientationPatient" not in ds:
            return list(dicom_paths)
        iop = np.array(ds.ImageOrientationPatient, dtype=float)
        normal = np.cross(iop[:3], iop[3:])
        keys.append(float(np.dot(np.array(ds.ImagePositionPatient, dtype=float), normal)))
    return [p for _, p in sorted(zip(keys, dicom_paths, strict=True), key=lambda t: t[0])]


def _image_to_volume(image: sitk.Image) -> Volume:
    array = sitk.GetArrayFromImage(image)  # shape (z, y, x)
    sx, sy, sz = image.GetSpacing()  # SimpleITK da (x, y, z)
    return Volume(
        pixel_array=array,
        spacing=(sz, sy, sx),
        direction=tuple(float(v) for v in image.GetDirection()),
        origin=tuple(float(v) for v in image.GetOrigin()),
    )


def volume_to_image(volume: Volume) -> sitk.Image:
    """Publica (sin "_") a proposito -- tambien la reusa
    infrastructure/dicom/simpleitk_volume_serializer.py para escribir NIfTI,
    sin duplicar la conversion de ejes/spacing."""
    image = sitk.GetImageFromArray(volume.pixel_array)  # espera (z, y, x)
    sz, sy, sx = volume.spacing
    image.SetSpacing((sx, sy, sz))  # SimpleITK espera (x, y, z)
    image.SetDirection(volume.direction)
    image.SetOrigin(volume.origin)
    return image
