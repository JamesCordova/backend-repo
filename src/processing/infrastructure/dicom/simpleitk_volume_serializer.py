from pathlib import Path

import SimpleITK as sitk

from processing.application.ports.volume_serializer import VolumeSerializer
from processing.domain.entities import Volume
from processing.infrastructure.dicom.simpleitk_volume_processor import volume_to_image


class SimpleItkVolumeSerializer(VolumeSerializer):
    """Escribe el volumen como NIfTI comprimido (.nii.gz) -- formato que ya
    sabe leer el frontend (volume-renderer-ts, via nifti-reader-js), cerrando
    la decision de formato que quedaba pendiente (seccion 20 del documento de
    arquitectura). Reusa SimpleITK, ya una dependencia para leer DICOM, en vez
    de agregar una libreria nueva (ej. nibabel) solo para escribir NIfTI --
    SimpleITK soporta el formato nativamente, sin IO adicional."""

    def save(self, volume: Volume, path: Path) -> None:
        image = volume_to_image(volume)
        sitk.WriteImage(image, str(path))
