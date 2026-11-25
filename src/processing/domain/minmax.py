"""Normalizacion generica (recorte + escala a [0,1]) -- regla de negocio
pura, sin I/O, mismo criterio que domain/hounsfield.py. Para datos SIN
calibracion fisica conocida (ej. un volumen .raw sin cabecera, sin
RescaleSlope/Intercept) -- normalize_hounsfield asume una escala Hounsfield
real con una ventana fija; aca hay dos variantes:

- normalize_range: el caller declara el rango [min, max] a mostrar (ej. un
  .raw de 16 bits que SI es HU real conocido, aunque no calibrado via tags
  DICOM) -- misma formula que normalize_hounsfield, nombre generico porque
  no asume que las unidades son HU.
- normalize_minmax: sin rango declarado, usa el minimo/maximo observado en
  los propios datos -- el caso por defecto cuando no se sabe nada de la
  escala de origen (ej. un .raw de 8 bits ya pre-procesado para visualizar).
"""

import numpy as np

from processing.domain.entities import Volume


def normalize_range(volume: Volume, min_value: float, max_value: float) -> Volume:
    """Recorta el volumen a [min_value, max_value] y lo escala a [0, 1].
    No modifica el spacing. Misma formula que normalize_hounsfield, pero sin
    asumir que los valores son Hounsfield units -- aplicable a cualquier
    escala de origen que el caller ya conozca."""
    if min_value >= max_value:
        raise ValueError(f"min_value ({min_value}) debe ser menor que max_value ({max_value})")

    clipped = np.clip(volume.pixel_array, min_value, max_value)
    scaled = (clipped - min_value) / (max_value - min_value)
    return Volume(pixel_array=scaled.astype(np.float32), spacing=volume.spacing)


def normalize_minmax(volume: Volume) -> Volume:
    """Escala el volumen a [0, 1] usando el minimo/maximo real de sus
    propios datos -- sin rango declarado de antemano. No modifica el
    spacing."""
    array = volume.pixel_array
    minimum = float(array.min())
    maximum = float(array.max())

    if maximum <= minimum:
        # Volumen constante (o vacio) -- no hay contraste que mostrar de
        # todas formas; evita division por cero devolviendo todo en 0 en vez
        # de lanzar, un volumen "plano" es un resultado valido, no un error.
        return Volume(
            pixel_array=np.zeros_like(array, dtype=np.float32), spacing=volume.spacing
        )

    return normalize_range(volume, minimum, maximum)
