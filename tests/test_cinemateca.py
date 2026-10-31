from datetime import date

from cartelera.scrapers import cinemateca

CALENDARIO = """
<h4 class="bg-black text-white">sábado 31</h4>
<div class="col-md-6 mb-3 d-flex"><img src="https://cinemateca.org.uy/img/1"/>
  <a class="text-secondary fw-bolder" href="/ciclos/907">Filmtage: Ciclo del Cine Alemán</a>
  <p class="mb-1"><a class="text-black fw-bolder" href="/peliculas/9651">Babystar</a></p>
  <p class="mb-1">de Joscha Bongard</p>
  <a href="#" class="kc_cinema_event_badge" data-event-id="100" data-film-id="40853"></a>
</div>
<h4 class="bg-black text-white">domingo 1</h4>
<div class="col-md-6 mb-3 d-flex">
  <p class="mb-1"><a class="text-black fw-bolder" href="/peliculas/9651">Babystar</a></p>
  <a href="#" class="kc_cinema_event_badge" data-event-id="101" data-film-id="40853"></a>
</div>
</section>
"""


def test_fechas_de_los_dias_cruzan_el_mes():
    assert cinemateca.fechas_de_los_dias([30, 31, 1, 2], date(2026, 10, 30)) == [
        date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1), date(2026, 11, 2),
    ]


def test_leer_calendario_agrupa_funciones_por_pelicula():
    peliculas = cinemateca.leer_calendario(CALENDARIO, date(2026, 10, 30))
    babystar = peliculas["9651"]
    assert babystar["titulo"] == "Babystar"
    assert babystar["ciclo"] == "Filmtage: Ciclo del Cine Alemán"
    assert babystar["director"] == "Joscha Bongard"
    assert babystar["funciones"] == [(date(2026, 10, 31), "100", "40853"), (date(2026, 11, 1), "101", "40853")]


def test_duracion_y_sinopsis():
    pagina = "<p>Duración:</p><p> 128 min.</p><h3>Sinopsis</h3><p>Maestra y militante.</p><footer>Síganos</footer>"
    assert cinemateca.duracion_y_sinopsis(pagina) == (128, "Maestra y militante.")


def test_tarifas_y_beneficios_del_recuadro_de_precios(pagina):
    precio, beneficios = cinemateca.tarifas(pagina("cinemateca_precios.html"))
    assert (precio.desde, precio.hasta) == (480, 480)  # la entrada general; la de socio es un beneficio
    assert {b.programa: b.tipo for b in beneficios} == {
        "Socios Cinemateca": "Precio de socio", "Socio Espectacular": "Socio Espectacular",
        "BROU": "2x1", "Udelar": "2x1", "la diaria": "2x1", "Antel": "2x1",
    }
