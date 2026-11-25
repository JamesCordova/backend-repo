"""Pruebas del adaptador real -- no requieren Docker (SimpleITK es una libreria
normal, no un servicio), pero si prueban el comportamiento real de la libreria
contra una serie DICOM sintetica con valores conocidos.
"""

import numpy as np
import pytest
from fixtures.synthetic_dicom import (
    PIXEL_SPACING_MM,
    RESCALE_INTERCEPT,
    RESCALE_SLOPE,
    SLICE_THICKNESS_MM,
    write_oriented_series,
)

from processing.infrastructure.dicom.simpleitk_volume_processor import SimpleItkVolumeProcessor


def test_load_series_aplica_rescale_a_hounsfield_units(synthetic_dicom_series):
    processor = SimpleItkVolumeProcessor()

    volume = processor.load_series(synthetic_dicom_series)

    # slice i tiene pixel crudo = i*10 -> hu esperado = i*10*slope + intercept
    expected_hu_per_slice = [i * 10 * RESCALE_SLOPE + RESCALE_INTERCEPT for i in range(4)]
    actual_hu_per_slice = [float(volume.pixel_array[i, 0, 0]) for i in range(4)]
    np.testing.assert_allclose(actual_hu_per_slice, expected_hu_per_slice)


def test_load_series_respeta_el_spacing_del_dicom(synthetic_dicom_series):
    processor = SimpleItkVolumeProcessor()

    volume = processor.load_series(synthetic_dicom_series)

    row_spacing, col_spacing = PIXEL_SPACING_MM
    np.testing.assert_allclose(volume.spacing, (SLICE_THICKNESS_MM, row_spacing, col_spacing))


def test_load_series_ordena_por_posicion_y_no_por_orden_de_archivo(synthetic_dicom_series):
    """Las exportaciones reales (ej. TCIA) no nombran los archivos en orden espacial: con la
    lista desordenada antes se apilaban los cortes mezclados y el spacing en z salia mal."""
    processor = SimpleItkVolumeProcessor()
    shuffled = [synthetic_dicom_series[i] for i in (2, 0, 3, 1)]

    volume = processor.load_series(shuffled)

    expected_hu_per_slice = [i * 10 * RESCALE_SLOPE + RESCALE_INTERCEPT for i in range(4)]
    actual_hu_per_slice = [float(volume.pixel_array[i, 0, 0]) for i in range(4)]
    np.testing.assert_allclose(actual_hu_per_slice, expected_hu_per_slice)
    assert volume.spacing[0] == SLICE_THICKNESS_MM


@pytest.mark.parametrize("name,iop,first", [
    # axial con las columnas hacia anterior: la normal apunta a inferior
    ("axial_invertido", (1, 0, 0, 0, -1, 0), (-10.0, 10.0, 20.0)),
    # coronal: filas a lo largo de x, columnas hacia inferior, cortes a lo largo de y
    ("coronal", (1, 0, 0, 0, 0, -1), (-10.0, -10.0, 20.0)),
])
def test_resample_reorienta_a_la_grilla_canonica(tmp_path, name, iop, first):
    """El volumen de salida queda alineado a los ejes (direccion identidad, LPS de ITK):
    el indice k crece hacia superior sin importar como se adquirio la serie (plan E.2)."""
    paths = write_oriented_series(tmp_path, iop, first, num_slices=21, rows=21, cols=21,
                                  pixel_spacing=1.0, slice_step=1.0)
    processor = SimpleItkVolumeProcessor()

    resampled = processor.resample_to_isotropic(processor.load_series(paths), target_spacing_mm=1.0)

    assert resampled.direction == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    arr = resampled.pixel_array  # (z, y, x)
    assert arr.shape == (21, 21, 21)
    per_slice = arr.reshape(arr.shape[0], -1)
    # constante dentro de cada corte axial y creciente hacia superior (10 por mm)
    np.testing.assert_allclose(per_slice.min(axis=1), per_slice.max(axis=1), atol=1e-3)
    np.testing.assert_allclose(np.diff(per_slice[:, 0]), 10.0, atol=1e-3)
    assert per_slice[0, 0] == pytest.approx(0.0)  # el corte inferior esta en S = 0 mm


def test_resample_to_isotropic_deja_spacing_igual_en_las_3_dimensiones(synthetic_dicom_series):
    processor = SimpleItkVolumeProcessor()
    volume = processor.load_series(synthetic_dicom_series)

    resampled = processor.resample_to_isotropic(volume, target_spacing_mm=1.0)

    np.testing.assert_allclose(resampled.spacing, (1.0, 1.0, 1.0))


def test_resample_to_isotropic_ajusta_el_shape_proporcionalmente(synthetic_dicom_series):
    processor = SimpleItkVolumeProcessor()
    volume = processor.load_series(synthetic_dicom_series)
    original_shape = volume.pixel_array.shape  # (z=4, y=8, x=8), spacing (2.0, 0.5, 0.5)

    resampled = processor.resample_to_isotropic(volume, target_spacing_mm=1.0)

    # spacing se duplica (0.5->1.0 en x/y) => shape en x/y se aproxima a la mitad;
    # spacing en z se reduce a la mitad (2.0->1.0) => shape en z se aproxima al doble
    assert resampled.pixel_array.shape[0] == round(original_shape[0] * 2.0 / 1.0)
    assert resampled.pixel_array.shape[1] == round(original_shape[1] * 0.5 / 1.0)
    assert resampled.pixel_array.shape[2] == round(original_shape[2] * 0.5 / 1.0)
