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

    def __post_init__(self) -> None:
        if self.pixel_array.ndim != 3:
            raise ValueError(f"se esperaba un array 3D, llego shape={self.pixel_array.shape}")
        if len(self.spacing) != 3:
            raise ValueError(f"spacing debe tener 3 componentes, llego {self.spacing}")
