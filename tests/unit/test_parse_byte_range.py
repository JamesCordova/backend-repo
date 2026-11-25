"""parse_byte_range es una funcion pura (sin FastAPI/Starlette) -- se prueba
aislada con casos conocidos de RFC 7233, igual que la normalizacion de
Hounsfield en worker-repo."""

import pytest

from application.errors import InvalidRangeError
from application.use_cases.get_study_volume import parse_byte_range


def test_sin_header_devuelve_none():
    assert parse_byte_range(None, total_size=1000) is None


def test_rango_explicito():
    assert parse_byte_range("bytes=0-99", total_size=1000) == (0, 99)


def test_rango_abierto_hasta_el_final():
    assert parse_byte_range("bytes=100-", total_size=1000) == (100, 999)


def test_rango_de_sufijo_ultimos_n_bytes():
    assert parse_byte_range("bytes=-500", total_size=1000) == (500, 999)


def test_rango_de_sufijo_mayor_al_total_se_recorta_a_todo():
    assert parse_byte_range("bytes=-5000", total_size=1000) == (0, 999)


def test_end_mas_alla_del_total_se_recorta():
    assert parse_byte_range("bytes=500-9999", total_size=1000) == (500, 999)


def test_ultimo_byte_exacto():
    assert parse_byte_range("bytes=999-999", total_size=1000) == (999, 999)


@pytest.mark.parametrize(
    "header",
    [
        "abc",
        "bytes=",
        "bytes=abc-def",
        "bytes=1000-1005",  # start >= total_size
        "bytes=500-100",  # start > end
        "bytes=0-1,2-3",  # multiples rangos, no soportado
        "bytes=-0",  # sufijo de 0 bytes, no tiene sentido
    ],
)
def test_rangos_invalidos_lanzan_invalid_range_error(header):
    with pytest.raises(InvalidRangeError):
        parse_byte_range(header, total_size=1000)


def test_sufijo_de_un_byte_es_valido():
    assert parse_byte_range("bytes=-1", total_size=1000) == (999, 999)


def test_invalid_range_error_lleva_el_total_size():
    with pytest.raises(InvalidRangeError) as exc_info:
        parse_byte_range("bytes=5000-6000", total_size=1000)
    assert exc_info.value.total_size == 1000
