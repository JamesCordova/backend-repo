"""Normalizacion de Hounsfield units: regla de negocio pura, sin I/O ni
dependencia de SimpleITK/pydicom -- por eso vive en domain y no detras de un
puerto de infrastructure, a diferencia de la lectura DICOM o el resampling
(que si necesitan una libreria de procesamiento de imagenes).
"""

import numpy as np

from processing.domain.entities import Volume


def normalize_hounsfield(volume: Volume, min_hu: float, max_hu: float) -> Volume:
    """Recorta el volumen a la ventana [min_hu, max_hu] y lo escala a [0, 1].
    No modifica el spacing.
    """
    if min_hu >= max_hu:
        raise ValueError(f"min_hu ({min_hu}) debe ser menor que max_hu ({max_hu})")

    clipped = np.clip(volume.pixel_array, min_hu, max_hu)
    scaled = (clipped - min_hu) / (max_hu - min_hu)
    return Volume(pixel_array=scaled.astype(np.float32), spacing=volume.spacing)
