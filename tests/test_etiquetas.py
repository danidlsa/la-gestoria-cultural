from datetime import timedelta

from cartelera.etiquetas import etiquetar
from cartelera.modelo import Evento, Funcion, Procedencia


def evento(titulo, lugar_id="sala", categoria="musica", dias=1, ahora=None, **extra):
    inicio = ahora + timedelta(days=dias)
    return Evento(
        id=titulo, titulo=titulo, categoria=categoria, lugar_id=lugar_id, funciones=[Funcion(inicio=inicio)],
        fuentes=[Procedencia(fuente="x", id_externo=titulo, url="https://x", visto=ahora)], actualizado=ahora, **extra,
    )


def test_ciclo_explicito_y_ciclo_por_prefijo_repetido(ahora):
    eventos = [
        evento("Ciclo de piano Raquel Boldorini", "teatro-solis", ahora=ahora),
        evento("Partículas: Miel + Malapraxxis", "sala-verdi", ahora=ahora),
        evento("Partículas: Ninguna Higuera", "sala-verdi", dias=3, ahora=ahora),
        evento("Rodrigo: un solo título con dos puntos", "otra-sala", ahora=ahora),
    ]
    ciclos = etiquetar(eventos, {})
    assert {c.titulo for c in ciclos} == {"Ciclo de piano Raquel Boldorini", "Partículas"}
    particulas = next(c for c in ciclos if c.titulo == "Partículas")
    assert particulas.cantidad == 2 and particulas.lugar_id == "sala-verdi"
    assert eventos[3].ciclo_id is None


def test_subcategorias_y_festivales(ahora):
    bns = evento("BNS - El Cascanueces", categoria="danza", ahora=ahora)
    stand_up = evento("Noche de Comedia de Stand Up", categoria="teatro", ahora=ahora)
    festival = evento("Festival Fado Mvd 2026", ahora=ahora)
    otro_ballet = evento("Gala 35 años Ballet AL", categoria="danza", ahora=ahora)
    etiquetar([bns, stand_up, festival, otro_ballet], {})
    assert bns.subcategoria == "ballet_sodre"
    assert (stand_up.subcategoria, stand_up.categoria) == ("stand_up", "humor")
    assert festival.etiquetas == ["festival"]
    assert otro_ballet.subcategoria is None
