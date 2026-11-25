import numpy as np

from processing.domain.entities import Volume
from processing.domain.hounsfield import normalize_hounsfield


def test_normaliza_al_rango_0_1():
    # -1000, 0, 1000 HU son los limites y el centro de la ventana de tejido blando
    raw = np.array([[[-1000.0, 0.0, 1000.0]]])
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_hounsfield(volume, min_hu=-1000.0, max_hu=1000.0)

    np.testing.assert_allclose(result.pixel_array.flatten(), [0.0, 0.5, 1.0])


def test_recorta_valores_fuera_de_la_ventana():
    raw = np.array([[[-2000.0, 5000.0]]])  # muy por fuera de [-1000, 1000]
    volume = Volume(pixel_array=raw, spacing=(1.0, 1.0, 1.0))

    result = normalize_hounsfield(volume, min_hu=-1000.0, max_hu=1000.0)

    np.testing.assert_allclose(result.pixel_array.flatten(), [0.0, 1.0])


def test_no_modifica_el_spacing():
    raw = np.zeros((2, 2, 2))
    volume = Volume(pixel_array=raw, spacing=(2.5, 1.0, 1.0))

    result = normalize_hounsfield(volume, min_hu=-1000.0, max_hu=1000.0)

    assert result.spacing == (2.5, 1.0, 1.0)
