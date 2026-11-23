"""Especiales con la grilla en una noticia (la Noche de los Cafés y Bares Notables 2026, del Municipio B)."""

from datetime import date, datetime

from cartelera import especiales
from cartelera.scrapers import notas_especiales

from tests.conftest import MONTEVIDEO

NOCHE = {
    "id": "noche-de-los-cafes-y-bares-notables", "nombre": "Noche de los Cafés y Bares Notables",
    "descripcion": "Ocho cafés y bares históricos.", "desde": date(2026, 11, 26), "horario": ["19:00", "01:00"],
    "pagina": "https://municipiob.montevideo.gub.uy/llega-la-primera-noche", "etiquetas": ["bar"],
    "regla": "meses", "meses": [11], "palabras": ["noche de (los )?cafes y bares notables", "bares notables"],
}
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=MONTEVIDEO)


def test_la_grilla_de_la_nota(pagina):
    eventos = notas_especiales.eventos_de_la_nota(pagina("municipio_b_noche_bares_notables.html"), NOCHE, AHORA)
    assert [(e.funciones[0].inicio.strftime("%H:%M"), e.titulo, e.lugar.nombre) for e in eventos] == [
        ("19:00", "Rossana Taddei, Gavilán presentando", "Café Brasilero"),
        ("19:30", "Trío de Tango", "Santa Catalina Bar Café"),
        ("20:00", "La Banda de Los Lunes", "Bar Paysandú"),
        ("21:00", "Trío Candombero", "Montevideo al Sur"),
        ("21:00", "FRIBO - Diego Pez & los Pernoctantes - Shows de bailes de Tango", "Bar Facal"),
        ("21:30", "Garo en vivo", "Bar Andorra"),
        ("22:00", "8 de Momo", "Bar Marbella"),
        # En la grilla es "Escaramuza"; en la lista de bares, con su nombre completo y su dirección.
        ("23:00", "Gonzalo Denis (Franny Glass)", "Escaramuza Libros y Café"),
    ]
    escaramuza, facal = eventos[-1], eventos[4]
    # Las esquinas, como las entiende el geocodificador.
    assert escaramuza.lugar.direccion == "Dr. Pablo de María y Charrúa"
    assert facal.lugar.direccion == "Av. 18 de Julio y Yi"
    assert all(e.ciclo == "Noche de los Cafés y Bares Notables 2026" and e.etiquetas == ["bar"] for e in eventos)
    assert all(e.categoria == "musica" and e.url == NOCHE["pagina"] and e.descripcion_corta is None for e in eventos)
    assert escaramuza.id_externo == "noche-de-los-cafes-y-bares-notables-2026-escaramuza-libros-y-cafe-2300"
    # Con el ciclo, el especial los encuentra.
    ventana = especiales.proxima_edicion(NOCHE, AHORA.date())["ventana"]
    como_eventos = [{"titulo": e.titulo, "ciclo_nombre": e.ciclo, "funciones": [{"inicio": e.funciones[0].inicio.isoformat()}]}
                    for e in eventos]
    assert len(especiales.actividades(NOCHE, ventana, como_eventos, {})) == 8


def test_una_nota_sin_grilla_es_un_error_y_lo_pasado_no_se_lee(monkeypatch, pagina):
    import pytest
    with pytest.raises(ValueError):
        notas_especiales.grilla_de("<h3>Otra cosa</h3><p>Nada - 21 horas - Bar</p>")
    leidas = []

    class Cliente:
        def texto(self, url):
            leidas.append(url)
            return pagina("municipio_b_noche_bares_notables.html")

    monkeypatch.setattr(especiales, "activo", lambda: True)
    monkeypatch.setattr(especiales, "cargar", lambda: [{**NOCHE, "nota": "https://n/1"}, {**NOCHE, "nota": "https://n/2", "desde": date(2026, 11, 1)}])
    eventos, errores = notas_especiales.scrapear(Cliente(), AHORA)
    assert (leidas, len(eventos), errores) == (["https://n/1"], 8, [])


def test_direccion_buscable():
    assert notas_especiales.direccion_buscable("Ituzaingó y 25 de Mayo") == "Ituzaingó y 25 de Mayo"
    assert notas_especiales.direccion_buscable("Rondeau esq. Paysandú") == "Rondeau y Paysandú"
