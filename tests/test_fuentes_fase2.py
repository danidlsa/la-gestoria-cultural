"""Fuentes de la fase 2: Sala del Museo, productoras (Gaucho, Piano Piano), beneficios de la diaria y Fever."""

import json
from datetime import date

from cartelera.extraer import fecha_sin_anio, jsonld_de_tipo
from cartelera.scrapers import fever, gaucho, ladiaria, piano_piano, sala_del_museo


def test_sala_del_museo_fecha_hora_y_enlace_a_redtickets(pagina, ahora):
    url = "https://www.saladelmuseo.com.uy/shows/item/coti.html"
    evento = sala_del_museo.parsear_ficha(pagina("sala_del_museo_show.html"), url, ahora)
    assert (evento.titulo, evento.categoria) == ("COTI", "musica")  # el "Museo del Carnaval" no lo hace carnaval
    assert evento.funciones[0].inicio.isoformat() == "2026-11-22T20:00:00-03:00"
    assert evento.enlaces == ["https://redtickets.uy/evento/COTI/32964/"]
    assert evento.imagen_url.startswith("https://www.saladelmuseo.com.uy/media/")


def test_gaucho_solo_lo_proximo_visible_y_en_montevideo(pagina, ahora):
    eventos = [e for s in json.loads(pagina("gaucho_shows.json")) if (e := gaucho.armar_evento(s, ahora))]
    assert [e.titulo for e in eventos] == ["Pixies"]
    pixies = eventos[0]
    assert pixies.funciones[0].inicio.isoformat() == "2027-04-02T21:00:00-03:00"
    assert (pixies.lugar.nombre, pixies.productor, pixies.entradas[0].via) == ("Teatro de Verano", "Gaucho", "tickantel")


def test_piano_piano_tipo_sala_y_sin_el_interior(pagina, ahora):
    tarjetas = piano_piano.leer_agenda(pagina("piano_piano_agenda.html"))
    eventos = {e.titulo: e for t in tarjetas if (e := piano_piano.armar_evento(t, ahora))}
    assert "No Te Va Gustar en Salto" not in eventos
    assert eventos["No Te Va Gustar"].lugar.nombre == "Velódromo Municipal"  # sin "en Montevideo" en el título
    assert (eventos["Boite"].categoria, eventos["Germán Medina"].categoria) == ("teatro", "humor")
    assert eventos["La Kermesse Redonda"].lugar.nombre == "Rural del Prado"  # tarjeta sin tipo: el pie es la sala


def test_la_diaria_beneficio_fechas_y_precio(pagina, ahora):
    items = ladiaria.items_del_feed(pagina("ladiaria_feed.xml"))
    eventos = [e for i in items if (e := ladiaria.armar_evento(i, ahora))]
    assert len(eventos) == 1  # la Fiesta de la Leche es en Cardal, Florida
    obra = eventos[0]
    assert (obra.lugar.nombre, obra.precio.desde) == ("Espacio Zorrilla", 660)
    assert obra.funciones[0].inicio.isoformat() == "2026-11-13T20:00:00-03:00"
    assert (obra.beneficios[0].programa, obra.beneficios[0].tipo) == ("la diaria", "2x1")
    assert obra.enlaces and "redtickets.uy/evento/" in obra.enlaces[0]


def test_fever_toma_el_evento_con_fecha(pagina, ahora):
    objeto = jsonld_de_tipo(pagina("fever_evento.html"), "Event")[0]
    evento = fever.armar_evento(objeto, ahora)
    assert (evento.titulo, evento.lugar.nombre) == ("Candlelight: Tributo a Joan Manuel Serrat", "Hyatt Centric")
    assert evento.funciones[0].inicio.isoformat() == "2026-11-08T16:30:00-03:00"
    assert evento.precio.desde == 1450


def test_fecha_sin_anio():
    hoy = date(2026, 10, 31)
    assert fecha_sin_anio(13, 11, hoy) == date(2026, 11, 13)
    assert fecha_sin_anio(9, 10, hoy) is None  # pasó hace unas semanas: no es del año que viene
    assert fecha_sin_anio(10, 4, hoy) == date(2027, 4, 10)


def test_teatro_de_verano_un_evento_por_etapa_de_carnaval(pagina):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from cartelera.scrapers import teatro_de_verano

    ahora = datetime(2026, 11, 11, 12, 0, tzinfo=ZoneInfo("America/Montevideo"))  # la etapa 1 ya pasó
    tarjeta = {"id": "136", "url": "https://teatrodeverano.montevideo.gub.uy/Programacion/Prueba-uc136",
               "titulo": "Prueba de Admisión - Carnaval 2027", "imagen": None}
    eventos = teatro_de_verano.eventos_por_etapa(tarjeta, pagina("teatro_de_verano_admision.html"), ahora)
    assert [e.titulo.split(" · ")[1].split(":")[0] for e in eventos] == [f"Etapa {n}" for n in range(2, 8)]
    assert eventos[-1].titulo.endswith("Etapa 7: Carambola, A la Bartola, Don Bochinche y Cía., Agarrate Catalina")
    ultima = eventos[-1]
    assert ultima.funciones[0].inicio.isoformat() == "2026-11-16T20:30:00-03:00"
    assert (ultima.categoria, ultima.precio.gratis) == ("carnaval", True)
    assert "Agarrate Catalina (murga)" in ultima.descripcion_corta
    assert "Inicio de espectáculo" not in ultima.descripcion_corta  # el pie de la página no es un conjunto
    assert "Ítacos (parodistas)" in eventos[1].descripcion_corta  # tildes y categorías de varias palabras
