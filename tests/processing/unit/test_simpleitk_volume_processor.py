"""Pruebas del adaptador real -- no requieren Docker (SimpleITK es una libreria
normal, no un servicio), pero si prueban el comportamiento real de la libreria
contra una serie DICOM sintetica con valores conocidos.
"""

import numpy as np
from fixtures.synthetic_dicom import (
    PIXEL_SPACING_MM,
    RESCALE_INTERCEPT,
    RESCALE_SLOPE,
    SLICE_THICKNESS_MM,
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
