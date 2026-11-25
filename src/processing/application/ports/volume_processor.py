from pathlib import Path
from typing import Protocol

from processing.domain.entities import Volume


class VolumeProcessor(Protocol):
    """Operaciones que si requieren una libreria de procesamiento de imagenes
    (SimpleITK). La normalizacion de Hounsfield NO esta aqui a proposito -- es
    una formula pura, ver domain/hounsfield.py.
    """

    def load_series(self, dicom_paths: list[Path]) -> Volume:
        """Lee una serie DICOM (multiples archivos, uno por slice) y devuelve
        un Volume ya en Hounsfield units (RescaleSlope/RescaleIntercept aplicados)."""
        ...

    def resample_to_isotropic(self, volume: Volume, target_spacing_mm: float) -> Volume:
        """Reinterpola el volumen a espaciado isotropico (mismo mm en z, y, x)."""
        ...
