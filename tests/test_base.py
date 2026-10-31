from datetime import datetime

from cartelera.modelo import EventoCrudo, LugarCrudo, ResultadoFuente
from cartelera.scrapers import base


def _resultado(cantidad: int, ok: bool = True) -> ResultadoFuente:
    eventos = [
        EventoCrudo(fuente="prueba", id_externo=str(i), url=f"https://x/{i}", titulo=f"Evento {i}",
                    lugar=LugarCrudo(nombre="Sala"), funciones=[])
        for i in range(cantidad)
    ]
    return ResultadoFuente(fuente="prueba", corrida=datetime.now().astimezone(), ok=ok, cantidad=cantidad, eventos=eventos)


def test_conserva_el_resultado_anterior_si_cae_mucho(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "DIR_FUENTES", tmp_path)
    assert base.guardar(_resultado(100))
    assert not base.guardar(_resultado(20))
    assert base.cargar("prueba").cantidad == 100


def test_conserva_el_resultado_anterior_si_la_corrida_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "DIR_FUENTES", tmp_path)
    assert base.guardar(_resultado(30))
    assert not base.guardar(_resultado(0, ok=False))
    assert base.cargar("prueba").cantidad == 30


def test_acepta_variaciones_normales(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "DIR_FUENTES", tmp_path)
    assert base.guardar(_resultado(100))
    assert base.guardar(_resultado(80))
