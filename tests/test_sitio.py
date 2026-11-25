import pytest

from cartelera.sitio.generar import en_cartel, fecha_corta, precio_texto, presupuesto


@pytest.mark.parametrize("precio, esperado", [
    ({"gratis": True}, "gratis"),
    ({"desde": 0, "hasta": 0}, "gratis"),
    ({"desde": 0, "hasta": 990}, "ganga"),  # una entrada a $0 entre pagas no hace gratis al evento
    ({"desde": 450}, "ganga"),
    ({"desde": 500}, "accesible"),
    ({"desde": 999}, "accesible"),
    ({"desde": 1000}, "normal"),
    ({"desde": 1600}, "normal"),
    ({"desde": 1601}, "carito"),
    ({"desde": None}, None),
    (None, None),
])
def test_presupuesto(precio, esperado):
    assert presupuesto(precio) == esperado


def test_textos():
    assert fecha_corta("2026-10-30T17:30:00-03:00") == "vie 30 oct · 17:30"
    assert fecha_corta("2026-11-01T00:00:00-03:00", sin_hora=True) == "dom 1 nov"
    assert precio_texto({"desde": 650, "hasta": 1200}) == "$650 a $1.200"
    assert precio_texto({"gratis": True}) == "Gratis"


def _con_dias(*dias):
    return {"funciones": [{"inicio": f"{d}T20:00:00-03:00"} for d in dias]}


def test_en_cartel():
    temporada = _con_dias(*[f"2026-11-{d:02d}" for d in (6, 7, 8, 13, 14, 15, 20, 21)])
    assert en_cartel(temporada)
    assert not en_cartel(_con_dias("2026-11-06", "2026-11-07", "2026-11-08"))  # pocas fechas
    assert not en_cartel(_con_dias(*[f"2026-11-{d:02d}" for d in range(1, 9)]))  # muchas, pero en una semana


def test_markdown_de_la_pestana_que_es():
    from cartelera.sitio.generar import markdown_simple
    salida = markdown_simple("Hola <b>!\n\n- [Tickantel](https://tickantel.com.uy), **ticketera**\n- Otra\n\nChau,\nDaniela")
    assert "<p>Hola &lt;b&gt;!</p>" in salida
    assert '<ul><li><a href="https://tickantel.com.uy">Tickantel</a>, <strong>ticketera</strong></li><li>Otra</li></ul>' in salida
    assert "<p>Chau,<br>Daniela</p>" in salida


def test_markdown_cada_pregunta_es_desplegable():
    from cartelera.sitio.generar import markdown_simple
    salida = str(markdown_simple("Hola\n\n# ¿Qué es?\n\nUn sitio.\n\n# ¿Cómo?\n\nAsí.\n\n---\n\nChau"))
    assert salida.count('<details class="pregunta" open><summary><h2>') == 2
    assert salida.index("<p>Hola</p>") < salida.index("<details")  # la presentación queda afuera
    assert salida.rstrip().endswith("</details>\n<p>Chau</p>")  # la despedida, después de "---", también


def test_markdown_no_deja_pasar_enlaces_que_no_son_web():
    from cartelera.sitio.generar import markdown_simple
    salida = markdown_simple("[malo](javascript:alert(1)) [bueno](https://x.uy) [interno](que-es.html) [mail](mailto:a@b.uy)")
    assert "javascript" not in salida.split("[malo]")[0] and 'href="javascript' not in salida
    assert 'href="https://x.uy"' in salida and 'href="que-es.html"' in salida and 'href="mailto:a@b.uy"' in salida


def test_los_enlaces_de_las_fuentes_tienen_que_ser_web():
    import pytest
    from pydantic import ValidationError
    from cartelera.modelo import Entrada, LugarCrudo, EventoCrudo
    with pytest.raises(ValidationError):
        Entrada(url="javascript:alert(1)", via="x")
    evento = EventoCrudo(fuente="x", id_externo="1", url="https://x.uy/1", titulo="T", lugar=LugarCrudo(nombre="L"),
                         funciones=[], imagen_url="data:image/svg+xml,<svg onload=alert(1)>")
    assert evento.imagen_url is None



def test_rock_y_pop_va_con_otros_en_los_generos():
    from cartelera.sitio.generar import datos_para_el_navegador
    base = {"titulo": "X", "lugar_id": "l", "fuentes": [{"url": "https://x.uy"}], "funciones": [{"inicio": "2026-11-01T20:00:00-03:00"}]}
    eventos = [dict(base, id="1", categoria="musica", subcategoria="rock_pop"), dict(base, id="2", categoria="musica", subcategoria="clasica")]
    datos = datos_para_el_navegador(eventos, {"l": {"nombre": "L"}}, [])
    assert [e["sub"] for e in datos["eventos"]] == [None, "clasica"]
    assert datos["subcategoriasOtros"]["musica"] == "Rock, pop y otros"


def test_el_buscador_encuentra_el_nombre_del_ciclo():
    from cartelera.sitio.generar import datos_para_el_navegador
    evento = {"id": "1", "titulo": "La caja negra", "categoria": "cine", "lugar_id": "l", "ciclo_id": "c1",
              "fuentes": [{"url": "https://x.uy"}], "funciones": [{"inicio": "2026-11-11T19:00:00-03:00"}]}
    datos = datos_para_el_navegador([evento], {"l": {"nombre": "Terminal Goes"}}, [{"id": "c1", "titulo": "Ciclo de Cine Accesible 2026"}])
    assert "Cine Accesible" in datos["eventos"][0]["texto"]


def test_un_solo_enlace_y_nunca_la_cartelera():
    from cartelera.sitio.generar import entrada_principal, promos_ordenadas
    fuentes = [{"fuente": "cartelera_mvd", "url": "https://cartelera.montevideo.com.uy/x"}]
    evento = {"fuentes": fuentes, "entradas": [
        {"via": "cartelera_mvd", "url": "https://cartelera.montevideo.com.uy/x"},
        {"via": "solis", "url": "https://teatrosolis.org.uy/x"},
        {"via": "tickantel", "url": "https://tickantel.com.uy/x"},
        {"via": "redtickets", "url": "https://redtickets.uy/y"},
    ]}
    assert entrada_principal(evento)["via"] == "tickantel"  # la ticketera, aunque la sala venga antes
    assert entrada_principal({"fuentes": fuentes, "entradas": evento["entradas"][:2]})["via"] == "solis"
    assert entrada_principal({"fuentes": fuentes, "entradas": evento["entradas"][:1]}) is None
    promos = promos_ordenadas({"beneficios": [{"programa": "Otras promos"}, {"programa": "la diaria"}]})
    assert [p["programa"] for p in promos] == ["la diaria", "Otras promos"]


def test_periodo_de_una_exposicion():
    from datetime import date, timedelta
    from cartelera.sitio.generar import periodo_muestra
    hoy, despues = date.today().isoformat(), (date.today() + timedelta(days=28)).isoformat()
    assert periodo_muestra({"funciones": [{"inicio": hoy + "T00:00:00-03:00"}], "hasta": "2027-02-28"}) == "Hasta el 28 feb 2027"
    assert periodo_muestra({"funciones": [{"inicio": hoy + "T00:00:00-03:00"}], "hasta": None}) == "En exhibición"
    assert periodo_muestra({"funciones": [{"inicio": despues + "T00:00:00-03:00"}], "hasta": None}).startswith("Desde el ")


def test_robots_y_sitemap_para_buscadores():
    from cartelera.sitio.generar import robots_txt, sitemap_xml
    assert "Sitemap: https://ejemplo.uy/sitemap.xml" in robots_txt("https://ejemplo.uy/")
    mapa = sitemap_xml("https://ejemplo.uy/", "2026-11-02")
    assert "<loc>https://ejemplo.uy/</loc><lastmod>2026-11-02</lastmod>" in mapa
    assert "<loc>https://ejemplo.uy/que-es.html</loc>" in mapa


def test_donde_pasa_la_config_es_valida():
    import tomllib
    from cartelera.donde_pasa import CONFIG, cargar
    nombres, de_lugar = cargar()
    assert set(nombres) == {"bares", "espacios", "chicas", "grandes", "aire_libre"}  # "no aplica" no se muestra
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    todos = [lugar for grupo in config.values() for lugar in grupo["lugares"]]
    assert len(todos) == len(set(todos)), "un lugar está en dos grupos"
    assert de_lugar["the-shannon-irish-pub"] == "bares" and de_lugar["teatro-solis"] == "grandes"


def test_donde_pasa_avisa_de_los_lugares_sin_etiqueta(tmp_path):
    from cartelera import donde_pasa
    config = tmp_path / "donde_pasa.toml"
    config.write_text('[bares]\nnombre = "Bares y cafés"\nlugares = ["the-shannon"]\n\n'
                      '[no_aplica]\nnombre = "No aplica"\nlugares = ["cinemateca"]\n', encoding="utf-8")
    evento = lambda lugar, titulo: {"lugar_id": lugar, "titulo": titulo, "categoria": "musica",
                                    "funciones": [{"inicio": "2026-11-20T21:00:00-03:00"}], "fuentes": [{"url": "https://x.uy/"}]}
    eventos = [evento("the-shannon", "Open mic"), evento("cinemateca", "Una película"),
               evento("sala-nueva", "Banda A"), evento("sala-nueva", "Banda B")]
    items = donde_pasa.pendientes(eventos, {"sala-nueva": {"nombre": "Sala Nueva", "direccion": "Soriano 1"}}, config)
    assert [(i["id"], i["cantidad"]) for i in items] == [("sala-nueva", 2)]  # ni el clasificado ni el de "no aplica"
    cuerpo = donde_pasa.cuerpo(items)
    assert "**Sala Nueva** (Soriano 1) · `sala-nueva` · 2 eventos" in cuerpo and "<!-- lugar:sala-nueva -->" in cuerpo


def test_el_precio_para_ordenar_por_precio():
    from cartelera.sitio.generar import datos_para_el_navegador
    base = {"titulo": "X", "categoria": "musica", "lugar_id": "l", "fuentes": [{"url": "https://x.uy"}],
            "funciones": [{"inicio": "2026-11-01T20:00:00-03:00"}]}
    eventos = [dict(base, id="1", precio={"desde": 0, "hasta": 0, "gratis": True}),
               dict(base, id="2", precio={"desde": 700, "hasta": 800, "gratis": False}), dict(base, id="3")]
    datos = datos_para_el_navegador(eventos, {"l": {"nombre": "L"}}, [])
    assert [e["precioDesde"] for e in datos["eventos"]] == [0, 700, None]  # sin precio: al final


def test_un_especial_con_su_fecha_ya_pasada_no_se_muestra():
    # Sábados en Ciudad Vieja es todos los meses: con la fecha elegida (21/11) ya pasada, no salta al mes siguiente.
    from datetime import date, datetime
    from cartelera import especiales
    from cartelera.scrapers.base import MONTEVIDEO
    fin = especiales.termina({"hasta": date(2026, 11, 21), "estimada": False, "a_confirmar": False, "horario": None})
    assert fin == datetime(2026, 11, 22, 0, 0, tzinfo=MONTEVIDEO)


def test_periodo_de_una_muestra_con_inauguracion():
    from datetime import date, timedelta
    from cartelera.sitio.generar import periodo_muestra
    dia = date.today() + timedelta(days=8)
    funciones = [{"inicio": f"{dia}T19:00:00-03:00", "sin_hora": False}, {"inicio": f"{dia + timedelta(days=1)}T00:00:00-03:00", "sin_hora": True}]
    assert periodo_muestra({"funciones": funciones, "hasta": None}).startswith("Inaugura el ")
    assert periodo_muestra({"funciones": funciones, "hasta": None}).endswith(" · 19:00")
    assert periodo_muestra({"funciones": funciones[1:], "hasta": None}).startswith("Desde el ")
