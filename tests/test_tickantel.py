from datetime import datetime, timedelta

from cartelera.scrapers import tickantel

URL = "https://tickantel.com.uy/ng/espectaculo/40021761/rasgar-la-tierra"


def test_parsea_funciones_lugar_y_precio(pagina, ahora):
    evento = tickantel.parsear_espectaculo(pagina("tickantel_espectaculo.html"), URL, ahora)

    assert evento.id_externo == "40021761"
    assert evento.titulo == "Rasgar la tierra"
    assert evento.categoria == "teatro"
    assert evento.lugar.nombre == "Teatro Solís"
    assert (evento.lugar.lat, evento.lugar.lon) == (-34.90786, -56.20101)
    assert evento.precio.desde == 550
    assert evento.funciones[0].inicio == datetime.fromisoformat("2026-10-30T17:30:00-03:00")
    assert evento.funciones == sorted(evento.funciones, key=lambda f: f.inicio)
    assert tickantel.incluir(evento)


def test_descarta_funciones_pasadas(pagina, ahora):
    mucho_despues = ahora + timedelta(days=60)
    assert tickantel.parsear_espectaculo(pagina("tickantel_espectaculo.html"), URL, mucho_despues) is None


def test_lee_el_sitemap():
    sitemap = "<urlset><url><loc>https://tickantel.com.uy/ng/espectaculo/1/a</loc></url>" \
              "<url><loc> https://tickantel.com.uy/ng/espectaculo/1/a </loc></url></urlset>"
    assert tickantel.urls_de_espectaculos(sitemap) == ["https://tickantel.com.uy/ng/espectaculo/1/a"]


def test_id_de_url_con_alta_demanda():
    assert tickantel.id_de_url("https://tickantel.com.uy/ng/espectaculo/alta-demanda/40021784/la-trampa") == "40021784"


def test_descarta_funciones_con_aviso_de_cancelacion(pagina, ahora):
    # El JSON-LD dice EventScheduled, pero cada función trae "Espectáculo cancelado".
    url = "https://tickantel.com.uy/ng/espectaculo/40021331/mosquitos"
    assert tickantel.parsear_espectaculo(pagina("tickantel_cancelado.html"), url, ahora) is None
