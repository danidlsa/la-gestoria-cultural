from datetime import date
from zoneinfo import ZoneInfo

from cartelera.scrapers import cartelera_mvd, mvd_cms

MVD = ZoneInfo("America/Montevideo")
HOY = date(2026, 10, 30)


def test_funciones_de_texto_varias_fechas_sin_hora():
    funciones = mvd_cms.funciones_de_texto("30 y 31 de octubre / 1, 7 y 8 de noviembre", HOY, MVD)
    assert [f.inicio.date().isoformat() for f in funciones] == [
        "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-07", "2026-11-08",
    ]
    assert all(f.sin_hora for f in funciones)


def test_funciones_de_texto_con_hora_y_cambio_de_anio():
    (funcion,) = mvd_cms.funciones_de_texto("16 de febrero, 20:30h", HOY, MVD)
    assert funcion.inicio.isoformat() == "2027-02-16T20:30:00-03:00"
    assert not funcion.sin_hora


def test_fecha_de_la_cartelera():
    assert cartelera_mvd.fecha_de("Viernes 30 de Octubre", HOY) == date(2026, 10, 30)
    assert cartelera_mvd.fecha_de("Sábado 9 de Enero", HOY) == date(2027, 1, 9)
    assert cartelera_mvd.fecha_de("sin fecha", HOY) is None


def test_precio_de_las_localidades():
    precio = cartelera_mvd.precio_de("$ 600 - Promo 2 x $ 800 - La Diaria 2x1. En venta en RedTickets.")
    assert (precio.desde, precio.hasta) == (600, 600)
    assert cartelera_mvd.precio_de("Entrada libre y gratuita").gratis
    assert cartelera_mvd.precio_de("Consultar en boletería") is None
