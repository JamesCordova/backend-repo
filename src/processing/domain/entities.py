"""Entidades de dominio del worker. Sin imports de SimpleITK/pydicom/Celery --
solo numpy, que aqui se trata como "tipo de dato basico" (igual que list o
dict), no como un framework de infraestructura.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class ProcessingTaskStatus(str, Enum):
    """Espejo de processing_tasks.status en api-repo (seccion 21 del documento
    de arquitectura). Duplicado deliberado -- ver seccion 1.3: solo entidades
    puras cruzan la frontera entre repos, nunca codigo compartido por import.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Volume:
    """Un volumen 3D con su espaciado fisico. `spacing` es (z, y, x) en mm por
    voxel -- mismo orden que las dimensiones de `pixel_array` (slices, alto, ancho).
    """

    pixel_array: np.ndarray  # shape (z, y, x), valores en Hounsfield units
    spacing: tuple[float, float, float]
    # Geometria en el espacio del paciente, convencion de ITK/DICOM (LPS, mm) y orden
    # (x, y, z): direction son los cosenos directores 3x3 por filas (columna i = hacia
    # donde crece el indice x), origin es el centro del voxel (0, 0, 0). Por defecto
    # identidad/cero: un RAW no trae orientacion. Se conservan hasta el remuestreo, que
    # deja el volumen en la grilla canonica (direccion identidad), ver plan E.2.
    direction: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if self.pixel_array.ndim != 3:
            raise ValueError(f"se esperaba un array 3D, llego shape={self.pixel_array.shape}")
        if len(self.spacing) != 3:
            raise ValueError(f"spacing debe tener 3 componentes, llego {self.spacing}")
