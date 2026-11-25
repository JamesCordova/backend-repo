from pathlib import Path

import SimpleITK as sitk

from processing.application.ports.volume_processor import VolumeProcessor
from processing.domain.entities import Volume


class SimpleItkVolumeProcessor(VolumeProcessor):
    def load_series(self, dicom_paths: list[Path]) -> Volume:
        # sitk.ImageSeriesReader aplica RescaleSlope/RescaleIntercept del DICOM
        # automaticamente -- el array resultante ya viene en Hounsfield units,
        # no en valores crudos de pixel.
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames([str(p) for p in dicom_paths])
        image = reader.Execute()
        return _image_to_volume(image)

    def resample_to_isotropic(self, volume: Volume, target_spacing_mm: float) -> Volume:
        image = volume_to_image(volume)
        original_size = image.GetSize()
        original_spacing = image.GetSpacing()

        new_spacing = (target_spacing_mm, target_spacing_mm, target_spacing_mm)
        new_size = [
            max(1, round(original_size[i] * original_spacing[i] / new_spacing[i]))
            for i in range(3)
        ]

        resampled = sitk.Resample(
            image,
            new_size,
            sitk.Transform(),
            sitk.sitkLinear,
            image.GetOrigin(),
            new_spacing,
            image.GetDirection(),
            0.0,
            image.GetPixelID(),
        )
        return _image_to_volume(resampled)


def _image_to_volume(image: sitk.Image) -> Volume:
    array = sitk.GetArrayFromImage(image)  # shape (z, y, x)
    sx, sy, sz = image.GetSpacing()  # SimpleITK da (x, y, z)
    return Volume(pixel_array=array, spacing=(sz, sy, sx))


def volume_to_image(volume: Volume) -> sitk.Image:
    """Publica (sin "_") a proposito -- tambien la reusa
    infrastructure/dicom/simpleitk_volume_serializer.py para escribir NIfTI,
    sin duplicar la conversion de ejes/spacing."""
    image = sitk.GetImageFromArray(volume.pixel_array)  # espera (z, y, x)
    sz, sy, sx = volume.spacing
    image.SetSpacing((sx, sy, sz))  # SimpleITK espera (x, y, z)
    return image
