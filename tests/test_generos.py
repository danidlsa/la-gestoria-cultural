"""Géneros gruesos de la música: palabras clave y respaldo con Wikidata (sin red: caché y correcciones)."""

import json

from cartelera import generos
from cartelera.etiquetas import etiquetar
from tests.test_etiquetas import evento


def test_genero_por_palabras_con_titulo_antes_que_descripcion(ahora):
    eventos = [
        evento("Idilio", productor="Orquesta Sinfónica Nacional del Sodre", ahora=ahora),
        evento("Noche de cumbia y plena", ahora=ahora),
        evento("Cordera", descripcion_corta="Una mezcla única de rock, cumbia y ritmos latinos", ahora=ahora),
        evento("Trotsky Vengarán", descripcion_corta="Punk rock uruguayo", ahora=ahora),
        # "plena validez" no es plena, y una orquesta de tango no es música clásica
        evento("Sosa 100 años", descripcion_corta="Con su orquesta. La entrada mantendrá plena validez", ahora=ahora),
        evento("Obra con rock", categoria="teatro", ahora=ahora),
    ]
    etiquetar(eventos, {})
    assert [e.subcategoria for e in eventos] == ["clasica", "tropical", "rock_pop", "rock_pop", None, None]


def test_artistas_probables_de_un_titulo():
    assert generos.artistas_probables("Marty Friedman en MMBOX - 15/11") == ["Marty Friedman en MMBOX", "Marty Friedman"]
    assert generos.artistas_probables("BELLAVISTA presenta 'Lo Que Puedo'") == ["BELLAVISTA"]
    assert generos.artistas_probables("TRIBUTO A OASIS SUPERNOVA") == ["OASIS SUPERNOVA", "OASIS"]
    assert generos.artistas_probables("24° Premios Graffiti") == []


def test_genero_mas_votado_entre_las_etiquetas_de_wikidata():
    assert generos.genero_de_etiquetas(["punk", "hard rock", "cumbia"]) == "rock_pop"
    assert generos.genero_de_etiquetas(["jazz", "Candombe"]) is None


def test_usa_la_cache_y_las_correcciones_sin_consultar(tmp_path, monkeypatch, ahora):
    cache = tmp_path / "generos.json"
    cache.write_text(json.dumps({
        "artistas": {"eruca sativa": {"id": "Q1", "generos": ["Q11"], "fecha": "2026-10-31T10:00:00"}},
        "generos": {"Q11": "rock alternativo"},
    }))
    monkeypatch.setattr(generos, "CACHE", cache)
    monkeypatch.setattr(generos, "MAX_CONSULTAS", 0)  # si intentara consultar, no podría
    buscar = generos.BuscadorDeGeneros(correcciones={"alejandro balbis": None, "golem": "rock_pop"})
    assert buscar("ERUCA SATIVA") == "rock_pop"
    assert buscar("Alejandro Balbis. Milonga por vos") is None
    assert buscar("Golem presenta: A Tale of Dust and Tide") == "rock_pop"
    assert buscar("Artista desconocido") is None
