import pytest

from cartelera import beneficios
from cartelera.scrapers import redtickets

URL = "https://www.redtickets.uy/evento/LA-REBELION-DE-LA-CARNE-Sala-Cero/34406/"


def test_parsea_categoria_lugar_y_funciones(pagina, ahora):
    evento = redtickets.parsear_evento(pagina("redtickets_evento.html"), URL, "34406", ahora)

    assert evento.titulo == "LA REBELIÓN DE LA CARNE (Sala Cero)"
    assert evento.categoria == "teatro"
    assert evento.categoria_segura
    assert evento.lugar.nombre == "Teatro El Galpón"
    assert evento.lugar.direccion == "Av. 18 de Julio 1618"
    assert (evento.lugar.lat, evento.lugar.lon) == (-34.90403, -56.181082)
    assert evento.productor == "Teatro El Galpón"
    assert len(evento.funciones) == 10
    assert evento.funciones[0].inicio.isoformat() == "2026-11-14T20:30:00-03:00"
    assert not evento.funciones[0].sin_hora
    # Las cortesías y los beneficios no cuentan como precio general.
    assert (evento.precio.desde, evento.precio.hasta) == (650, 650)
    assert not evento.precio.gratis
    assert {(b.programa, b.tipo) for b in evento.beneficios} == {
        ("la diaria", "2x1"),
        ("Socio Espectacular", "Socio Espectacular, 50% OFF Socio Espectacular"),
        ("Socios El Galpón", "Socio El Galpón, 50% OFF Socio El Galpón"),
    }


def test_excluye_otras_ciudades(pagina, ahora):
    otra_ciudad = pagina("redtickets_evento.html").replace('"cityname": "Montevideo"', '"cityname": "Florida"')
    with pytest.raises(redtickets.Excluido):
        redtickets.parsear_evento(otra_ciudad, URL, "34406", ahora)


def test_excluye_categorias_fuera_de_la_cartelera(pagina, ahora):
    deporte = pagina("redtickets_evento.html").replace('"id": "6", "name": "Teatro"', '"id": "2", "name": "Deportes"')
    with pytest.raises(redtickets.Excluido):
        redtickets.parsear_evento(deporte, URL, "34406", ahora)


def test_ids_de_listado():
    portada = '<a href="/evento/COTI/32964/">Coti</a> {"Link":"/evento/COTI/32964/"} <a href="/evento/OTRO/1/">'
    assert redtickets.ids_de_listado(portada) == {"32964": "/evento/COTI/32964/", "1": "/evento/OTRO/1/"}


def test_punto():
    assert redtickets._punto("POINT (-56.181082 -34.90403)") == (-34.90403, -56.181082)
    assert redtickets._punto(None) == (None, None)


@pytest.mark.parametrize("entrada, programa", [
    ("2x1 La Diaria c/u", "la diaria"),
    ("2X1 Diraria", "la diaria"),
    ("Pre Venta 2x1 la diaria", "la diaria"),
    ("2x1 BROU", "BROU"),
    ("25% OFF Itaú Volar", "Itaú"),
    ("2X1  EL PAIS", "Club El País"),
    ("FUTUROCK 2X1 C/U", "Futurock"),
    ("2X1 AEBU", "AEBU"),
    ("2x1 Antel", "Antel"),
    ("2x1 comunidad Udelar", "Udelar"),
    ("Platea Antel Arena", None),
    ("Socio El Galpón", "Socios El Galpón"),
    ("50% OFF Socio El Galpón - Platea Central VIP A", "Socios El Galpón"),
    ("Socio Activo (Precio Final)", "Socios de la sala"),
    ("SILLA SOCIO SUVD", "Socios SUVD"),
    ("2x1 Socio ESNADE c/u", "Socios ESNADE"),
    ("2x1", "2x1 para todos"),
    ("PROMO 2X1 c/u", "2x1 para todos"),
    ("Promo 3x2 c/u", "Promo grupal"),
    ("Promo Dúo", "Promo grupal"),
    ("20%off", "Otras promos"),
    ("2X1 SINTEP", "Otras promos"),
    ("Promo REMAX", "Otras promos"),
    ("Promo 2 x $ 800", "Promo grupal"),
    ("Pre Venta", None),
    ("Hasta Agotar Limitadas", None),
    ("Futuro Pista", None),
    ("Promo Producción", None),
    ("Cortesia", None),
    ("General", None),
    ("Estudiantes 50% OFF", None),
    ("Montevideo Libre", None),
])
def test_programa_de_una_entrada(entrada, programa):
    assert beneficios.programa(entrada) == programa


class _ClienteFalso:
    def __init__(self, paginas):
        self.paginas = paginas

    def texto(self, url):
        numero = int(url.rsplit(",", 1)[1])
        return self.paginas[numero] if numero < len(self.paginas) else ""


def _item(id_, categoria):
    return (f'{{"SecuentialId":0,"Id":"{id_}","Title":"T{id_}","Link":"/evento/T{id_}/{id_}/",'
            f'"Category":"{categoria}"}} <a href="/evento/T{id_}/{id_}/">')


def test_listado_completo_recorre_paginas_y_descarta_categorias():
    paginas = [_item(1, "Teatro") + _item(2, "Deportes"), _item(3, "Música"), _item(3, "Música")]
    rutas = redtickets.listado_completo(_ClienteFalso(paginas))
    assert set(rutas) == {"1", "3"}


def test_reusar_evento_de_la_corrida_anterior_sin_lo_vencido(pagina, ahora):
    evento = redtickets.parsear_evento(pagina("redtickets_evento.html"), URL, "34406", ahora)
    despues = ahora.replace(month=11, day=20)
    reusado = redtickets._vigente_otra_vez(evento, despues)
    assert reusado.funciones[0].inicio.isoformat() == "2026-11-21T20:30:00-03:00"
    assert redtickets._vigente_otra_vez(evento, ahora.replace(year=2027)) is None


def test_una_entrada_puede_nombrar_varios_programas():
    assert beneficios.programas("BROU y La Diaria 2x1") == ["la diaria", "BROU"]
    assert beneficios.programas("Cortesia") == []
