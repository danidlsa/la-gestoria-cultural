"""Fuentes de música que sumamos el 4/11/2026: Sala Camacuá, MiEntrada, CobraTicket y Corchea."""

from datetime import datetime, time

from cartelera.extraer import jsonld_de_tipo
from cartelera.modelo import ResultadoFuente
from cartelera.scrapers import base, cobraticket, corchea, mientrada, salacamacua
from cartelera.scrapers.ladiaria import items_del_feed
from cartelera.unificar import clave_de_url

from tests.conftest import MONTEVIDEO


def _por_nombre(pagina: str) -> dict[str, dict]:
    return {e["name"]: e for e in jsonld_de_tipo(pagina, "Event")}


def test_salacamacua_hora_y_venta_de_la_ficha(pagina, ahora):
    eventos = _por_nombre(pagina("salacamacua_portada.html"))
    ficha = salacamacua.leer_ficha(pagina("salacamacua_ficha.html"))
    evento = salacamacua.armar_evento(eventos["Presentación INTRO FULL ALBUM"], ficha, ahora)
    assert evento.funciones[0].inicio.isoformat() == "2026-11-12T20:00:00-03:00"
    assert evento.lugar.nombre == "Sala Camacuá"
    # El link viejo de RedTickets ("//servlet/…?,33806") se arregla y se une con el evento de RedTickets.
    assert evento.entradas[0].via == "redtickets"
    assert clave_de_url(evento.entradas[0].url) == "redtickets:33806"
    assert evento.imagen_url.endswith("A3-digital.jpg")


def test_salacamacua_temporada_con_ticketera_no_se_inventa(pagina, ahora):
    eventos = _por_nombre(pagina("salacamacua_portada.html"))
    obra = next(e for nombre, e in eventos.items() if nombre.startswith("CARTOGRAF"))  # del 5 al 14 de noviembre
    ficha = {"hora": time(20, 30), "venta": "https://redtickets.uy/evento/X/34375/", "imagen": None}
    assert salacamacua.armar_evento(obra, ficha, ahora) is None  # las funciones exactas llegan por RedTickets
    sin_venta = salacamacua.armar_evento(obra, {**ficha, "venta": None}, ahora)
    assert len(sin_venta.funciones) == 10


def test_mientrada_agenda_y_ficha(pagina, ahora):
    tarjetas = {t["titulo"]: t for t in mientrada.leer_agenda(pagina("mientrada_agenda.html"))}
    assert tarjetas["CASSETTE 07.11"]["hora"] == time(23, 30)  # "Apertura 23:30 - Inicio 23:30"
    ficha = mientrada.leer_ficha(pagina("mientrada_ficha.html"))
    assert ficha["ciudad"] == "Montevideo"
    emile = mientrada.armar_evento(tarjetas["EMILE PRESENTA: MONA/IAMBP/MANUEL JELEN"], ficha, ahora)
    assert emile.funciones[0].inicio.isoformat() == "2026-11-06T23:59:00-03:00"
    assert (emile.lugar.nombre, emile.id_externo) == ("Emile", "30642")
    assert emile.descripcion_corta.startswith("ESTE VIERNES 6")
    assert clave_de_url(emile.url) == "mientrada:30642"
    # Una ficha que pone la ciudad en lugar de la sala no se puede ubicar.
    assert mientrada.armar_evento(tarjetas["LA NOCHE DEL TERROR EN QUINTA DE ARTEAGA"], ficha, ahora) is None
    # Lo del interior queda afuera aunque se cuele en la agenda.
    assert mientrada.armar_evento(tarjetas["CASSETTE 07.11"], {**ficha, "ciudad": "Salto"}, ahora) is None


def test_cobraticket_datos_de_sveltekit(pagina, ahora):
    proximos = cobraticket.datos_de_pagina(pagina("cobraticket_eventos.json"))["nextEvents"]
    assert proximos[0]["name"].strip() == "CLUB JUEVES"
    assert proximos[0]["location"]["name"] == "Lotus WTC"
    evento = cobraticket.armar_evento(cobraticket.datos_de_pagina(pagina("cobraticket_ficha.json")), ahora)
    assert (evento.titulo, evento.categoria, evento.categoria_segura) == ("MARIKOCRACIA CABARET", "fiesta", True)
    assert (evento.lugar.nombre, evento.lugar.direccion) == ("Zoba Club", "Bv. España 2218")
    assert evento.funciones[0].inicio.isoformat() == "2026-11-07T23:50:00-03:00"
    assert evento.funciones[0].fin.isoformat() == "2026-11-08T06:00:00-03:00"
    assert clave_de_url(evento.url) == "cobraticket:706242"


def test_cobraticket_sin_congresos_ni_punta_del_este(pagina, ahora):
    datos = cobraticket.datos_de_pagina(pagina("cobraticket_ficha.json"))
    congreso = {**datos, "props": {**datos["props"], "category": {"name": "Congresos"}}}
    assert cobraticket.armar_evento(congreso, ahora) is None
    punta = {**datos, "props": {**datos["props"], "location": {"name": "Narbona", "latlng": {"lat": -34.96, "lng": -54.94}}}}
    assert cobraticket.armar_evento(punta, ahora) is None


def test_corchea_campos_fechas_y_links(pagina, ahora):
    eventos = {e.titulo: e for i in items_del_feed(pagina("corchea_feed.xml")) if (e := corchea.armar_evento(i, ahora))}
    tango = eventos["Mujeres al Tango presenta a Manuela Hernández"]
    assert tango.funciones[0].inicio.isoformat() == "2026-11-04T21:00:00-03:00"
    assert (tango.lugar.nombre, tango.lugar.direccion, tango.precio.desde) == ("Sala Corchea", "Soriano 1243", 590)
    assert tango.entradas[0].via == "entradasfans"
    assert [f.inicio.day for f in eventos["Buceo Invisible"].funciones] == [12, 13]  # "12 y 13/11/2026"
    assert clave_de_url(eventos["Tero Tero"].entradas[0].url) == "tickantel:40021695"
    assert eventos["Agustín Casulo"].entradas[0].via == "redtickets"
    # Dos links de Tickantel distintos (uno de otro show): no se usa ninguno, para no unirlo mal.
    assert [e.via for e in eventos["Sofía Alvez + Animales de Poder"].entradas] == ["corchea"]
    # El título dice 10/11 y el campo Fecha 17/11: no se adivina cuál es.
    assert "Ninguna Higuera + Guadalupe Calzada" not in eventos
    assert "La Tabaré" not in eventos  # Politeama, en Canelones


def test_corchea_solo_en_su_horario_de_visitas(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "DIR_FUENTES", tmp_path)
    madrugada = datetime(2026, 11, 5, 6, 17, tzinfo=MONTEVIDEO)
    mediodia = datetime(2026, 11, 5, 12, 17, tzinfo=MONTEVIDEO)
    assert corchea.puede_correr(madrugada) and not corchea.puede_correr(mediodia)

    class SinPedidos:
        def texto(self, url):
            raise AssertionError("fuera de horario no se pide nada")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    anterior = ResultadoFuente(fuente="corchea", corrida=madrugada, ok=True, cantidad=0, eventos=[])
    base.guardar(anterior)
    resultado = base.correr(corchea, cliente=SinPedidos(), ahora=mediodia)
    assert resultado.ok and resultado.corrida == madrugada  # queda el de la madrugada


def test_entraste_solo_montevideo_y_con_sala():
    from datetime import datetime

    from cartelera.scrapers import entraste

    ahora = datetime(2026, 11, 6, 18, 0, tzinfo=MONTEVIDEO)
    from pathlib import Path

    pagina = (Path(__file__).parent / "fixtures" / "entraste_portada.html").read_text(encoding="utf-8")
    datos = entraste.eventos_de_pagina(pagina)
    assert sorted(d["id"] for d in datos) == [1, 2, 3, 4]  # sin repetir el que aparece en dos secciones
    eventos = {e.titulo: e for d in datos if (e := entraste.armar_evento(d, ahora))}
    assert set(eventos) == {"PARISEO LATIN CLUB - VIE 13 NOV", "Vermut Session"}  # PAWSA es en la Costa; Resilience no dice sala
    fiesta = eventos["PARISEO LATIN CLUB - VIE 13 NOV"]
    assert fiesta.funciones[0].inicio.isoformat() == "2026-11-13T23:59:00-03:00"  # de UTC a Montevideo
    assert (fiesta.categoria, fiesta.precio.desde, fiesta.precio.hasta) == ("fiesta", 300, 650)
    assert clave_de_url(fiesta.url) == "entraste:pariseo-vie-13-nov"
    vermut = eventos["Vermut Session"]
    assert (vermut.categoria, vermut.precio.gratis) == ("musica", True)  # a las 19:00 no es una fiesta


def test_tikzet_ficha_de_una_sala_chica(pagina):
    import json
    from datetime import datetime

    from cartelera.scrapers import tikzet

    ahora = datetime(2026, 11, 9, 12, 0, tzinfo=MONTEVIDEO)
    ficha = json.loads(pagina("tikzet_ficha.json"))
    ficha = ficha.get("event", ficha)
    evento = tikzet.armar_evento(ficha, ahora)
    assert (evento.titulo, evento.lugar.nombre, evento.lugar.direccion) == ("Homenaje a Gilberto Gil", "El Hormiguero", "San Salvador 1644")
    assert evento.funciones[0].inicio.isoformat() == "2026-11-12T21:00:00-03:00"  # de UTC a Montevideo
    assert (evento.categoria, evento.precio.desde) == ("musica", 350)
    assert clave_de_url(evento.url) == "tikzet:homenaje-a-gilberto-gil"
    # Fuera de Uruguay, cursos y rifas: afuera. Una productora no es la sala: queda la dirección.
    assert tikzet.armar_evento({**ficha, "country": 0}, ahora) is None
    assert tikzet.armar_evento({**ficha, "name": "Curso de Cocina Saludable"}, ahora) is None
    otra = tikzet.armar_evento({**ficha, "organization": {"name": "Green Producciones y Eventos"}, "address": "Buenos Aires 314"}, ahora)
    assert (otra.lugar.nombre, otra.productor) == ("Buenos Aires 314", "Green Producciones y Eventos")
