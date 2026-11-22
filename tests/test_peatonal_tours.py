from datetime import datetime

from cartelera.scrapers import peatonal_tours
from cartelera.scrapers.base import MONTEVIDEO

AHORA = datetime(2026, 11, 22, 18, 0, tzinfo=MONTEVIDEO)


def test_los_tours_con_fecha_por_venir(pagina):
    tours = peatonal_tours.tours_de(pagina("peatonal_tours_portada.html"))
    assert len(tours) == 4
    eventos = {e.titulo: e for t in tours if (e := peatonal_tours.evento_de(t, AHORA))}
    # "Misterios de la Ciudad Vieja" no tiene fecha: no sale.
    assert sorted(eventos) == ["Paseo Bello & Reborati", "Tour Patrimonial y arquitectónico", "Tour Religioso - edición Ciudad Vieja"]
    paseo = eventos["Paseo Bello & Reborati"]
    (funcion,) = paseo.funciones
    assert funcion.inicio.isoformat() == "2026-11-29T15:00:00-03:00"  # la web da la hora en UTC
    assert funcion.fin.isoformat() == "2026-11-29T16:30:00-03:00"  # dura 90 minutos
    assert paseo.categoria == "tour" and paseo.precio.desde == 500 and not paseo.precio.gratis
    assert paseo.lugar.nombre == "Plaza Gomensoro" and round(paseo.lugar.lat, 3) == -34.917
    assert paseo.url == "https://www.peatonaltours.uy/tour/2" and paseo.entradas[0].via == "peatonal_tours"
    assert eventos["Tour Patrimonial y arquitectónico"].precio.gratis


def test_lo_que_ya_paso_no_sale(pagina):
    tours = peatonal_tours.tours_de(pagina("peatonal_tours_portada.html"))
    despues = datetime(2026, 12, 1, 12, 0, tzinfo=MONTEVIDEO)
    assert [e.titulo for t in tours if (e := peatonal_tours.evento_de(t, despues))] == ["Tour Patrimonial y arquitectónico"]
