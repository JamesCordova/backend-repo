import numpy as np
import pytest

from processing.domain.entities import Volume
from processing.domain.minmax import normalize_minmax, normalize_range


def test_normaliza_al_rango_0_1_usando_el_min_max_real():
    raw = np.array([[[10.0, 20.0, 30.0]]])
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_minmax(volume)

    np.testing.assert_allclose(result.pixel_array.flatten(), [0.0, 0.5, 1.0])


def test_volumen_constante_devuelve_todo_cero_sin_dividir_por_cero():
    raw = np.full((2, 2, 2), 42.0)
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_minmax(volume)

    np.testing.assert_allclose(result.pixel_array, np.zeros((2, 2, 2)))


def test_no_modifica_el_spacing():
    raw = np.array([[[1.0, 2.0]]])
    volume = Volume(pixel_array=raw, spacing=(2.5, 1.0, 1.0))

    result = normalize_minmax(volume)

    assert result.spacing == (2.5, 1.0, 1.0)


def test_funciona_con_valores_enteros_de_8_bits():
    raw = np.array([[[0, 128, 255]]], dtype=np.uint8)
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_minmax(volume)

    np.testing.assert_allclose(result.pixel_array.flatten(), [0.0, 128 / 255, 1.0], atol=1e-6)


def test_normalize_range_recorta_y_escala_a_un_rango_declarado():
    # simula un .raw de 16 bits con HU real (aire=-1000, hueso=+1000),
    # ventana declarada por el usuario en vez de min-max automatico
    raw = np.array([[[-1000.0, 0.0, 1000.0]]])
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_range(volume, min_value=-1000.0, max_value=1000.0)

    np.testing.assert_allclose(result.pixel_array.flatten(), [0.0, 0.5, 1.0])


def test_normalize_range_recorta_valores_fuera_de_la_ventana():
    raw = np.array([[[-2000.0, 5000.0]]])
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_range(volume, min_value=-1000.0, max_value=1000.0)

    np.testing.assert_allclose(result.pixel_array.flatten(), [0.0, 1.0])


def test_normalize_range_rechaza_min_mayor_o_igual_a_max():
    raw = np.zeros((2, 2, 2))
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    with pytest.raises(ValueError, match="debe ser menor"):
        normalize_range(volume, min_value=100.0, max_value=100.0)
