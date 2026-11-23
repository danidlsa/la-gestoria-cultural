import io
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from PIL import Image

from cartelera.scrapers import instagram_bares as ig

MVD = ZoneInfo("America/Montevideo")
AHORA = datetime(2026, 11, 10, 13, 0, tzinfo=MVD)


def funciones(texto, publicado=AHORA, ahora=AHORA):
    return [f.strftime("%d/%m %H:%M") for f in ig.leer_funciones(texto, publicado, ahora)]


def test_dia_y_hora_en_varias_formas():
    assert funciones("Jueves 12 y viernes 13 de noviembre\n21:30 h · Entrada $300") == ["12/11 21:30", "13/11 21:30"]
    assert funciones("Agenda:\nMiércoles 11 – Stand up 21h\nViernes 13 – Banda 23 hs") == ["11/11 21:00", "13/11 23:00"]
    assert funciones("Tocamos el 20/11 a las 22") == ["20/11 22:00"]
    assert funciones("HOY fiesta de disfraces a las 23") == ["10/11 23:00"]
    publicado = datetime(2026, 10, 24, 15, 0, tzinfo=MVD)
    assert funciones("Lunes otra vez. Presentación del libro, a las 19.30 h", publicado, publicado) == ["26/10 19:30"]


def test_la_hora_del_show_y_la_madrugada():
    assert funciones("Este viernes en vivo. Puerta 21 hs, show 22 hs") == ["13/11 22:00"]
    assert funciones("Sábado 14 – DJ set 00:30") == ["15/11 00:30"]  # la madrugada del domingo


def test_lo_que_no_es_un_evento():
    assert funciones("Lunes a viernes desde las 18h\nSábados desde las 20h") == []  # horario del bar
    assert funciones("de lunes a domingos nuestra cocina esta abierta para venir a almorzar\n\nte esperamos desde las 12 am") == []
    assert funciones("Nuestro menú ejecutivo, el lunes 16 desde las 12 h") == []
    assert funciones("Todos los jueves karaoke desde las 21h") == []
    assert funciones("Sorteo! Mañana anunciamos el ganador") == []  # sin hora
    assert funciones("Cerramos del 20/12 al 5/1") == []
    assert funciones("Jueves 5 de noviembre a las 21") == []  # ya pasó
    assert funciones("Viernes 13 – a las 5") == []  # a las 5 de la mañana: seguro es otra cosa
    assert funciones("Johnnie Walker te invita un trago hasta las 21 hs. Viernes 13, desde las 22") == ["13/11 22:00"]


def test_titulo_sin_adornos():
    assert ig.titulo_de("🎷 JAZZ EN EL BAR 🎷\nJueves 12", "bar") == "JAZZ EN EL BAR"
    assert ig.titulo_de("#jazz @alguien\n✨✨\nNoche de tango", "bar") == "Noche de tango"
    assert ig.titulo_de("🔥🔥", "Bar X") == "En Bar X"


def test_las_casillas_del_aviso():
    cuerpo = (
        "- [x] **Jazz en el bar** · Bar · jue 12/11 21:30 · [ver el post](https://x) <!-- ig:bar-1 -->\n"
        "  > texto\n"
        "- [ ] **Otra cosa** · Bar · vie 13/11 22:00 · [ver el post](https://y) <!-- ig:bar-2 -->\n"
        "- [X] **Título corregido a mano** · Bar · sáb 14/11 21:00 · [ver el post](https://z) <!-- ig:bar-3 -->\n"
    )
    aprobados, avisados = ig.leer_casillas([cuerpo])
    assert aprobados == {"bar-1": "Jazz en el bar", "bar-3": "Título corregido a mano"}
    assert avisados == {"bar-1", "bar-2", "bar-3"}
    # Lo que escribe el aviso se puede volver a leer.
    b = {"id": "bar-9", "titulo": "Show **con** asteriscos", "lugar": "Bar", "texto": "algo",
         "funciones": [{"inicio": "2026-11-12T21:30:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/1/", "usuario": "bar"}
    renglon = ig.renglon_del_borrador(b).replace("- [ ]", "- [x]")
    assert ig.leer_casillas([renglon])[0] == {"bar-9": "Show con asteriscos"}


def _jpeg():
    salida = io.BytesIO()
    Image.new("RGB", (40, 40), "orange").save(salida, "JPEG")
    return salida.getvalue()


def test_una_corrida(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "elbar"\n\n[[bar]]\nusuario = "personal"\n')
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "clave-de-prueba")
    posts = [
        {"id": "1", "caption": "🎷 Jazz en el bar\nJueves 12, 21:30 h. Entrada $300", "media_type": "IMAGE",
         "media_url": "https://cdn.example/1.jpg", "permalink": "https://www.instagram.com/p/1/",
         "timestamp": "2026-11-09T15:00:00+0000"},
        {"id": "2", "caption": "Abrimos de lunes a viernes desde las 18h", "media_type": "IMAGE",
         "media_url": "https://cdn.example/2.jpg", "permalink": "https://www.instagram.com/p/2/",
         "timestamp": "2026-11-09T15:00:00+0000"},
    ]
    claves_vistas = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        claves_vistas.append((pedido.url.host, pedido.headers.get("authorization")))
        if pedido.url.host == "cdn.example":
            return httpx.Response(200, content=_jpeg())
        if pedido.url.path.endswith("/me"):
            return httpx.Response(200, json={"instagram_business_account": {"id": "999"}})
        if "personal" in pedido.url.params["fields"]:
            return httpx.Response(400, json={"error": {"message": "Invalid user id", "code": 110}})
        return httpx.Response(200, json={"business_discovery": {"name": "El Bar", "media": {"data": posts}}})

    monkeypatch.setattr(ig, "TRANSPORTE", httpx.MockTransport(responder))

    # Primera corrida: nada tildado todavía. Queda un borrador (el horario del bar no) y no se publica nada.
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [])
    eventos, errores = ig.scrapear(None, AHORA)
    assert eventos == [] and errores == []
    borradores = json.loads(ig.BORRADORES.read_text())
    assert [b["titulo"] for b in borradores] == ["Jazz en el bar"]

    # Se tilda en el aviso (con otro título): en la corrida siguiente se publica, con la imagen guardada aparte.
    renglon = ig.renglon_del_borrador(borradores[0]).replace("- [ ]", "- [x]").replace("Jazz en el bar", "Jazz con Trío X")
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [{"number": 1, "state": "OPEN", "body": renglon}])
    eventos, errores = ig.scrapear(None, AHORA)
    assert errores == []
    (evento,) = eventos
    assert evento.titulo == "Jazz con Trío X" and evento.lugar.nombre == "El Bar"
    assert evento.entradas[0].via == "instagram" and evento.precio.desde == 300
    assert evento.imagen_url.startswith("https://lagestoriacultural.uy/afiches/instagram/")
    assert len(list(ig.DIR_AFICHES.glob("*.jpg"))) == 1
    # La clave va solo a la API de Meta, nunca al servidor de imágenes.
    assert ("cdn.example", None) in claves_vistas
    assert all(clave == "Bearer clave-de-prueba" for host, clave in claves_vistas if host == "graph.facebook.com")

    # Si la cuenta deja de publicarlo, sigue (está aprobado); si se saca la cuenta de la lista, se va.
    posts[:] = []
    assert [e.titulo for e in ig.scrapear(None, AHORA)[0]] == ["Jazz con Trío X"]
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "personal"\n')
    assert ig.scrapear(None, AHORA)[0] == []
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "elbar"\n\n[[bar]]\nusuario = "personal"\n')
    posts[:] = [{"id": "1", "caption": "🎷 Jazz en el bar\nJueves 12, 21:30 h. Entrada $300", "media_type": "IMAGE",
                 "media_url": "https://cdn.example/1.jpg", "permalink": "https://www.instagram.com/p/1/",
                 "timestamp": "2026-11-09T15:00:00+0000"}]
    assert [e.titulo for e in ig.scrapear(None, AHORA)[0]] == ["Jazz con Trío X"]

    # Si se saca el tilde, se va (y su imagen también).
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [{"number": 1, "state": "OPEN", "body": renglon.replace("[x]", "[ ]")}])
    eventos, _ = ig.scrapear(None, AHORA)
    assert eventos == [] and not list(ig.DIR_AFICHES.glob("*.jpg"))


def test_sin_clave_la_corrida_falla_y_queda_lo_anterior(monkeypatch):
    import pytest
    monkeypatch.delenv("INSTAGRAM_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        ig.scrapear(None, AHORA)


def test_el_aviso_solo_trae_lo_nuevo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b = {"id": "bar-1", "usuario": "bar", "titulo": "Jazz", "lugar": "Bar", "texto": "Jueves 12 21h",
         "funciones": [{"inicio": "2026-11-12T21:00:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/1/"}
    ig.guardar_borradores({"bar-1": b, "bar-2": {**b, "id": "bar-2", "titulo": "Otro"}})
    ya_avisado = ig.renglon_del_borrador(b)
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [{"number": 3, "state": "OPEN", "body": ya_avisado}])
    llamados = []
    monkeypatch.setattr(ig.subprocess, "run", lambda comando, **_: llamados.append(comando))
    monkeypatch.setenv("GH_REPO", "duena/repo")
    nuevos = ig.avisar(en_github=True, ahora=AHORA)
    assert [n["id"] for n in nuevos] == ["bar-2"]
    (crear,) = [c for c in llamados if c[:3] == ["gh", "issue", "create"]]
    assert "Otro" in crear[crear.index("--body") + 1] and crear[crear.index("--assignee") + 1] == "duena"
    assert not [c for c in llamados if c[:3] == ["gh", "issue", "close"]]  # sigue vigente


def test_con_una_clave_de_usuario_tambien_encuentra_la_cuenta():
    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/me"):
            return httpx.Response(400, json={"error": {"message": "nonexisting field (instagram_business_account)", "code": 100}})
        return httpx.Response(200, json={"data": {"granular_scopes": [
            {"scope": "pages_show_list", "target_ids": ["111"]}, {"scope": "instagram_basic", "target_ids": ["999"]}]}})
    with httpx.Client(transport=httpx.MockTransport(responder)) as http:
        assert ig.cuenta_de_la_gestoria(http, "clave") == "999"


def test_el_mismo_evento_en_varios_posts_es_un_borrador_y_el_lugar_sale_del_pin():
    cuenta = {"usuario": "mbc"}
    perfil = {"name": "Montevideo Beer Company"}
    def post(i, dia, texto):
        return {"id": str(i), "caption": texto, "media_type": "IMAGE", "media_url": f"https://cdn/{i}.jpg",
                "permalink": f"https://www.instagram.com/p/{i}/", "timestamp": f"2026-11-0{dia}T15:00:00+0000"}
    (a,) = ig.borradores_del_post(post(1, 3, "Festejamos 10 años!\n📅 13 de noviembre 21 hs\n📍 Museo Oceanográfico 🥃 trago"), cuenta, perfil, AHORA)
    (b,) = ig.borradores_del_post(post(2, 8, "Se suma otra banda!\n13 de noviembre, 21 hs\n📍Museo Oceanográfico"), cuenta, perfil, AHORA)
    assert a["id"] == b["id"] == "mbc-20261113"
    (sin_pin,) = ig.borradores_del_post(post(5, 9, "Una década de planes merecía una noche así, con todo\n13 de noviembre 21 hs"), cuenta, perfil, AHORA)
    junto = ig.juntar(ig.juntar(a, b), sin_pin)
    assert junto["titulo"] == "Montevideo Beer Company: Se suma otra banda" and len(junto["posts"]) == 3  # el título más corto
    assert junto["url"].endswith("/5/")  # el enlace principal, el post más reciente
    assert junto["lugar"] == "Museo Oceanográfico" and junto["barrio"] is None  # aunque el último post no traiga 📍
    renglon = ig.renglon_del_borrador(junto)
    assert "(y 2 posts más sobre lo mismo)" in renglon and "`mbc`" in renglon and "@mbc" not in renglon
    # Un 📍 que nombra al mismo bar deja el bar, con la dirección si la trae.
    (c,) = ig.borradores_del_post(post(3, 8, "Show 20/11 21h\n📍La Cretina, Soriano 1236"), {"usuario": "lacretinacasa", "nombre": "La Cretina"}, {}, AHORA)
    assert (c["lugar"], c["direccion"]) == ("La Cretina", "Soriano 1236")
    # Dos horas para el mismo día: queda una sola función.
    (d,) = ig.borradores_del_post(post(4, 8, "El domingo 6 de diciembre, a las 20 horas.\n🗓️ Domingo 6 de diciembre\n🎶 19:00 h"), cuenta, perfil, AHORA)
    assert len(d["funciones"]) == 1


SHANNON_MES = """Calendario de espectáculos de Noviembre 2026

Miércoles 4: OPEN MIC
Jueves 5: A CONFIRMAR
Miércoles 11: OPEN MIC
Jueves 12: SPAGUETTI WESTERN
Viernes 13: PROYECTO OLDIES
Club Shannon: VOLDCAST, ATROPELLO y SABOTAJE
Sábado 14: MORRIGAN'S
Jueves 26: A CONFIRMAR"""

SHANNON_SEMANA = """Estimados, les presentamos el calendario de espectáculos de la semana!!!!!

Miércoles 11/Noviembre:
OPEN MIC NIGHT - 4ta temporada
Bienvenidos al primer Open Mic de Uruguay. Participa, compartí tu arte.
Entrada libre 21:30hrs

Viernes 13/Noviembre:
PROYECTO OLDIES
Rock - 22 hs
Cubierto artístico $350"""


def _post(i, texto, dia="2026-11-04"):
    return {"id": str(i), "caption": texto, "media_type": "IMAGE", "media_url": f"https://cdn/{i}.jpg",
            "permalink": f"https://www.instagram.com/p/{i}/", "timestamp": f"{dia}T15:00:00+0000"}


def test_una_agenda_es_un_borrador_por_dia():
    cuenta, perfil = {"usuario": "theshannonuy"}, {"name": "The Shannon"}
    mes = ig.borradores_del_post(_post(1, SHANNON_MES), cuenta, perfil, AHORA)
    assert [(b["titulo"], b["funciones"][0]["sin_hora"]) for b in mes] == [
        ("The Shannon: OPEN MIC", True), ("The Shannon: SPAGUETTI WESTERN", True), ("The Shannon: PROYECTO OLDIES", True),
        ("The Shannon: MORRIGAN'S", True)]
    assert "VOLDCAST" in mes[2]["extracto"]  # lo de la otra sala del mismo día va en la descripción
    semana = ig.borradores_del_post(_post(2, SHANNON_SEMANA, "2026-11-09"), cuenta, perfil, AHORA)
    assert [(b["titulo"], b["funciones"][0]["inicio"][11:16]) for b in semana] == [
        ("The Shannon: OPEN MIC NIGHT", "21:30"), ("The Shannon: PROYECTO OLDIES", "22:00")]
    # La agenda del mes y la de la semana hablan del mismo día: queda uno, con la hora de la de la semana.
    assert mes[2]["id"] == semana[1]["id"] == "theshannonuy-20261113"
    junto = ig.juntar(mes[2], semana[1])
    assert junto["funciones"] == [{"inicio": "2026-11-13T22:00:00-03:00", "sin_hora": False}]
    assert "miércoles 11/11, **sin hora**" in ig.renglon_del_borrador(mes[0], AHORA)
    evento = ig.evento_de(semana[1], AHORA)
    assert evento.precio.desde == 350 and evento.titulo == "The Shannon: PROYECTO OLDIES"


def test_la_agenda_del_mingus():
    texto = ("Musica y toques de esta semana en El Mingus:\n\nMartes 10 de noviembre: Martes de Jazz (todos los martes)\n\n"
             "Miércoles 11 de Noviembre: Jazz & Bossa\n\nSábado 14 de noviembre (al mediodía): Piano Bar \n\n"
             "Reservá tu mesa via Whatsapp al 093 651 305.")
    lista = ig.borradores_del_post(_post(1, texto, "2026-11-09"), {"usuario": "el.mingus"}, {"name": "El Mingus"}, AHORA)
    assert [(b["titulo"], b["funciones"][0]["sin_hora"]) for b in lista] == [
        ("El Mingus: Martes de Jazz", True), ("El Mingus: Jazz & Bossa", True), ("El Mingus: Piano Bar", False)]
    assert lista[2]["funciones"][0]["inicio"][11:16] == "12:00"  # al mediodía


def test_un_dia_con_numero_sin_hora_entra_como_hora_a_confirmar():
    (b,) = ig.borradores_del_post(_post(1, "Cumplimos 12 años. El 29 de noviembre nos vemos en la calle", "2026-11-09"),
                                  {"usuario": "bar"}, {}, AHORA)
    assert b["funciones"] == [{"inicio": "2026-11-29T00:00:00-03:00", "sin_hora": True}]
    # Pero "el viernes" sin hora, o un período, no.
    assert ig.borradores_del_post(_post(2, "Este viernes nos vemos", "2026-11-09"), {"usuario": "bar"}, {}, AHORA) == []
    assert ig.borradores_del_post(_post(3, "Cerramos del 20/12 al 5/1", "2026-11-09"), {"usuario": "bar"}, {}, AHORA) == []



def test_lo_que_mostraron_los_posts_reales():
    cuenta = {"usuario": "bar"}
    # Un ciclo: "Martes de noviembre / 21:00 h" son todos los martes que quedan del mes.
    (taberna,) = ig.borradores_del_post(_post(1, "Se acerca el cierre pero aún quedan martes y mucha música.\n\n"
                                                 "Martes de noviembre / 21:00 h.\nEntrada libre.", "2026-11-09"), cuenta, {}, AHORA)
    assert [f["inicio"][:16] for f in taberna["funciones"]] == ["2026-11-10T21:00", "2026-11-17T21:00", "2026-11-24T21:00"]
    # Un sorteo no es un evento, aunque diga "jueves 12/11".
    sorteo = "Sorteamos una mesa para 10 personas.\n\nAnunciamos ganador el jueves 12/11 👀\n\nVálido hasta el 31/12/2026."
    assert ig.borradores_del_post(_post(2, sorteo, "2026-11-09"), cuenta, {}, AHORA) == []
    # Títulos sin la fecha, sin propaganda y con el nombre de abajo si es corto.
    assert ig.titulo_de("Este miércoles en Noches De Ensayos Abiertos\n\nLali Gaspari\n\nMúsica y compositora.", "x") == \
        "Noches De Ensayos Abiertos · Lali Gaspari"
    assert ig.titulo_de("FERIADO + MONKELIS I 2 DE DICIEMBRE EN LA CRETINA\n\n@feriado.uy se presenta", "x") == "FERIADO + MONKELIS"
    assert ig.titulo_de("🍻🎧 ¡ENTRADA GRATIS! INSCRIBITE EN EL LINK DE NUESTRA BIO.\nLa noche tiene dos lados", "x") == \
        "La noche tiene dos lados"
    assert ig.titulo_de("Este viernes 13 de noviembre celebramos la Noche de las Librerías en Mercado Ferrando", "x") == \
        "Celebramos la Noche de las Librerías en Mercado Ferrando"
    # Dos horas para el mismo día: la que aparece primero (el afiche de Mané dice 20 h).
    mane = ("El próximo domingo 6 de diciembre, a las 20 horas, Mané abre las puertas.\n\n"
            "📍 LA CRETINA\n🗓️ Domingo 6 de diciembre\n🎶 19:00 h")
    (b,) = ig.borradores_del_post(_post(3, mane), {"usuario": "lacretinacasa", "nombre": "La Cretina"}, {}, AHORA)
    assert b["funciones"][0]["inicio"][11:16] == "20:00"
    # El ciclo del mes y el post de un martes se juntan sin perder días.
    (un_martes,) = ig.borradores_del_post(_post(4, "Qué martes se viene\nMartes 10 de noviembre / 21:00 h.", "2026-11-10"), cuenta, {}, AHORA)
    assert len(ig.juntar(taberna, un_martes)["funciones"]) == 3


def test_lo_que_ya_no_sale_se_va_salvo_lo_aprobado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "elbar"\n')
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "x")
    viejo = {"id": "elbar-20261120", "usuario": "elbar", "titulo": "Sorteo", "lugar": "Bar", "texto": "t",
             "funciones": [{"inicio": "2026-11-20T21:00:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/9/",
             "posts": ["https://www.instagram.com/p/9/"]}
    ig.guardar_borradores({"elbar-20261120": viejo, "elbar-20261125": {**viejo, "id": "elbar-20261125", "aprobado": True,
                           "funciones": [{"inicio": "2026-11-25T21:00:00-03:00", "sin_hora": False}]}})

    def responder(pedido):
        if pedido.url.path.endswith("/me"):
            return httpx.Response(200, json={"instagram_business_account": {"id": "1"}})
        return httpx.Response(200, json={"business_discovery": {"name": "Bar", "media": {"data": []}}})

    monkeypatch.setattr(ig, "TRANSPORTE", httpx.MockTransport(responder))
    monkeypatch.setattr(ig, "avisos_en_github", lambda: None)  # sin GitHub: valen las decisiones guardadas
    eventos, _ = ig.scrapear(None, AHORA)
    assert set(ig.cargar_borradores()) == {"elbar-20261125"} and [e.id_externo for e in eventos] == ["elbar-20261125"]
    # Si el post del aprobado se vuelve a leer y ya no da un evento (se aprobó por error), se va igual.
    almuerzo = {"id": "9", "caption": "De lunes a domingos nuestra cocina está abierta para venir a almorzar",
                "media_type": "IMAGE", "media_url": "https://cdn/9.jpg", "permalink": "https://www.instagram.com/p/9/",
                "timestamp": "2026-11-09T15:00:00+0000"}
    monkeypatch.setattr(ig, "TRANSPORTE", httpx.MockTransport(lambda pedido: httpx.Response(200, json=(
        {"instagram_business_account": {"id": "1"}} if pedido.url.path.endswith("/me")
        else {"business_discovery": {"name": "Bar", "media": {"data": [almuerzo]}}}))))
    eventos, _ = ig.scrapear(None, AHORA)
    assert ig.cargar_borradores() == {} and eventos == []



def test_el_nombre_del_bar_en_el_titulo():
    assert ig.nombre_corto("MBC | MONTEVIDEO BEER COMPANY") == "MBC"
    assert ig.nombre_corto("Brecha Bar y Café 🏳️‍🌈") == "Brecha Bar y Café"
    assert ig.nombre_corto("INMIGRANTES") == "Inmigrantes"
    assert ig.con_el_bar("SPAGUETTI WESTERN", "The Shannon") == "The Shannon: SPAGUETTI WESTERN"
    # Si el título ya lo nombra, no se repite.
    assert ig.con_el_bar("Celebramos la Noche de las Librerías en Mercado Ferrando", "Mercado Ferrando") == \
        "Celebramos la Noche de las Librerías en Mercado Ferrando"
    # El nombre corto de la lista de bares gana sobre el del perfil.
    (b,) = ig.borradores_del_post(_post(1, "Jueves 12: SPAGUETTI WESTERN 22 hs", "2026-11-09"),
                                  {"usuario": "theshannonuy", "corto": "The Shannon"}, {"name": "The Shannon irish pub"}, AHORA)
    assert b["titulo"] == "The Shannon: SPAGUETTI WESTERN" and b["lugar"] == "The Shannon irish pub"


MAMBO = """⚠️ Esta noche: MAMBO

🎭✨ ¡MAMBO!

Un retrato contemporáneo, mordaz, profundamente humano y de humor corrosivo.

Elenco: amaral2435 y laleochavarria
Dirección: alfredo.goldstein

🗓️ Funciones:
Noviembre:
miércoles 11 y 18 | lunes 30 (20:30 hs) 🗓️🕒
Diciembre:
lunes 7, 14 y 21 (20:30 hs) 🗓️🕒

📷 alejandropersichetti
Produce: weproducciones"""


def test_una_obra_con_varias_funciones_es_un_borrador():
    ahora = datetime(2026, 11, 11, 10, 0, tzinfo=MVD)
    (b,) = ig.borradores_del_post(_post(1, MAMBO, "2026-11-11"), {"usuario": "lacretinacasa", "corto": "La Cretina"}, {}, ahora)
    assert b["titulo"] == "La Cretina: MAMBO"
    assert [f["inicio"][:16] for f in b["funciones"]] == [
        "2026-11-11T20:30", "2026-11-18T20:30", "2026-11-30T20:30", "2026-12-07T20:30", "2026-12-14T20:30", "2026-12-21T20:30"]
    assert ig.fechas_explicitas("13, 14 y 15 de noviembre", AHORA.date()) == [
        (date(2026, 11, 13), True), (date(2026, 11, 14), True), (date(2026, 11, 15), True)]


def test_el_borrador_no_cambia_de_identificador_cuando_pasa_su_primer_dia():
    texto = "Se acerca el cierre pero aún quedan martes y mucha música.\n\nMartes de noviembre / 21:00 h."
    ayer = ig.borradores_del_post(_post(1, texto, "2026-11-09"), {"usuario": "bar"}, {}, datetime(2026, 11, 10, 12, tzinfo=MVD))
    hoy = ig.borradores_del_post(_post(1, texto, "2026-11-09"), {"usuario": "bar"}, {}, datetime(2026, 11, 11, 12, tzinfo=MVD))
    assert ayer[0]["id"] == hoy[0]["id"] == "bar-20261110"
    # El día que ya pasó no se publica.
    evento = ig.evento_de(hoy[0], datetime(2026, 11, 11, 12, tzinfo=MVD))
    assert [f.inicio.day for f in evento.funciones] == [17, 24]


def test_las_coordenadas_de_la_lista_de_bares():
    cuenta = {"usuario": "latabernadebrecha", "direccion": "Durazno y Jackson", "lat": -34.909634, "lon": -56.172902}
    (b,) = ig.borradores_del_post(_post(1, "Martes 17 de noviembre 21 h", "2026-11-11"), cuenta, {"name": "La Taberna de Brecha"}, AHORA)
    lugar = ig.evento_de(b, AHORA).lugar
    assert (lugar.direccion, lugar.lat, lugar.lon) == ("Durazno y Jackson", -34.909634, -56.172902)



def test_dos_posts_de_la_misma_obra_son_un_borrador():
    estreno = ("🎭 MAMBO | De Miguel Morillo\n\n📅 ESTRENO: Miércoles 21 de octubre – 20:30 hs\n📍 La Cretina (Soriano 1236)\n\n"
               "🗓️ FUNCIONES (20:30 hs):\n▪️ Octubre: Miércoles 21 y 28\n▪️ Noviembre: Miércoles 11 y 18 | Lunes 30\n"
               "▪️ Diciembre: Lunes 7, 14 y 21\n\n🎫 Venta de entradas: Red Tickets 🎟️")
    cuenta = {"usuario": "lacretinacasa", "corto": "La Cretina"}
    ahora = datetime(2026, 11, 11, 10, 0, tzinfo=MVD)
    (viejo,) = ig.borradores_del_post(_post(1, estreno, "2026-10-10"), cuenta, {}, ahora)
    (nuevo,) = ig.borradores_del_post(_post(2, MAMBO, "2026-11-11"), cuenta, {}, ahora)
    assert viejo["titulo"] == nuevo["titulo"] == "La Cretina: MAMBO"
    assert viejo["id"] != nuevo["id"]
    (junto,) = ig.juntar_parecidos({viejo["id"]: viejo, nuevo["id"]: nuevo}).values()
    assert junto["id"] == viejo["id"] and len(junto["posts"]) == 2
    assert all(f["inicio"][11:16] == "20:30" for f in junto["funciones"])


def test_la_etiqueta_bares():
    (en_el_bar,) = ig.borradores_del_post(_post(1, "Jueves 12: SPAGUETTI WESTERN 22 hs", "2026-11-09"), {"usuario": "theshannonuy"}, {}, AHORA)
    assert ig.evento_de(en_el_bar, AHORA).etiquetas == ["bar"]
    # En otro lugar (📍), o en una cuenta que no es de un bar, no.
    (afuera,) = ig.borradores_del_post(_post(2, "13 de noviembre 21 hs\n📍 Museo Oceanográfico", "2026-11-09"), {"usuario": "mbc"}, {"name": "MBC"}, AHORA)
    (sala,) = ig.borradores_del_post(_post(3, "Sábado 14 de noviembre 21 hs", "2026-11-09"), {"usuario": "sala.ducon", "bar": False}, {}, AHORA)
    assert ig.evento_de(afuera, AHORA).etiquetas == [] and ig.evento_de(sala, AHORA).etiquetas == []


def test_la_cuenta_del_lugar(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "theshannonuy"\ndireccion = "Bartolomé Mitre 1318"\n'
                                         '[[bar]]\nusuario = "mbc"\ndireccion = "Ombú 1234"\n'
                                         '[[bar]]\nusuario = "unaferia"\nitinerante = true\n', encoding="utf-8")
    (en_el_bar,) = ig.borradores_del_post(_post(1, "Jueves 12: SPAGUETTI WESTERN 22 hs", "2026-11-09"), {"usuario": "theshannonuy"}, {}, AHORA)
    (afuera,) = ig.borradores_del_post(_post(2, "13 de noviembre 21 hs\n📍 Museo Oceanográfico", "2026-11-09"), {"usuario": "mbc"}, {"name": "MBC"}, AHORA)
    (feria,) = ig.borradores_del_post(_post(3, "Sábado 14 de noviembre 17 hs", "2026-11-09"), {"usuario": "unaferia", "itinerante": True}, {}, AHORA)
    # El lugar del evento es la cuenta solo si es en el bar; en otro lado (📍) o de una cuenta sin lugar fijo, no.
    assert [ig.evento_de(b, AHORA).lugar.instagram for b in (en_el_bar, afuera, feria)] == ["theshannonuy", None, None]


def test_las_horas_en_rango_y_las_convocatorias():
    assert funciones("Sábado 14 de noviembre, 13 (17-22h)") == ["14/11 17:00"]  # la feria abre a las 17
    assert funciones("Viernes 20/11 | 18.30 a 20.30 h") == ["20/11 18:30"]
    assert funciones("Sábado 14 de noviembre, de 14 a 20 hs") == ["14/11 14:00"]
    # Las fechas de una convocatoria son de inscripción, no de un evento.
    mes = ("Mes de las Migraciones\n18 de noviembre - 18 de diciembre\n✍️ Inscribí tu propuesta cultural-artística y "
           "participá de la agenda\n📅 Fecha límite: 15 de noviembre")
    assert ig.borradores_del_post(_post(1, mes, "2026-11-03"), {"usuario": "museomumi"}, {}, AHORA) == []
    assert funciones("Postulaciones hasta el viernes 20 de noviembre a las 18 h") == []
    # Una muestra abierta "del 18 de noviembre - 18 de diciembre" tampoco es un evento de cada día.
    assert funciones("Exposición abierta 18 de noviembre - 18 de diciembre, de 12 a 18 h") == []


def test_el_titulo_despues_de_un_encabezado():
    assert ig.titulo_de('INAUGURACIÓN EXPOSITIVA \n"La sal en las paredes"\n\n📅 Miércoles 18, 19h', "MuMI") \
        == 'Inauguración de "La sal en las paredes"'
    assert ig.titulo_de("NUEVA EDICIÓN! Laboratorio de escritura a cargo de terepuppo , para explorar otras maneras "
                        "de mirar, recordar, narrar y construir sentido.", "FAC") == "Laboratorio de escritura"


def test_el_lugar_sale_de_la_lista(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    (tmp_path / "bares.toml").write_text(
        '[[bar]]\nusuario = "museomumi"\nnombre = "MuMI - Muralla Abierta"\ndireccion = "Bartolomé Mitre 1550"\nbar = false\n\n'
        '[[bar]]\nusuario = "centroculturalterminalgoes"\nnombre = "Centro Cultural Terminal Goes"\n'
        'direccion = "Gral. Flores y Domingo Aramburú"\nlat = -34.882708\nlon = -56.181856\nbar = false\n', encoding="utf-8")
    feria = {"usuario": "feriadearteimpresomvd", "itinerante": True}
    # El 📍 "MuMi" es el MuMI de la lista, con su dirección.
    (b,) = ig.borradores_del_post(_post(1, "13, 14 y 15 de noviembre, 14-20h\n📍 MuMi – Muralla Abierta (Piedras y "
                                           "Bartolomé Mitre)", "2026-11-05"), feria, {}, AHORA)
    assert (b["lugar"], b["direccion"], b["bar"]) == ("MuMI - Muralla Abierta", "Bartolomé Mitre 1550", False)
    # Sin 📍, una cuenta sin lugar fijo puede nombrar al lugar por su usuario.
    (c,) = ig.borradores_del_post(_post(2, "Este Sábado 14 de Noviembre de 16 a 22 hs\n🏓 Plaza ex Terminal Goes "
                                           "centroculturalterminalgoes", "2026-11-11"), {"usuario": "feeldeagua", "itinerante": True},
                                  {}, AHORA)
    assert (c["lugar"], c["lat"], c["funciones"][0]["inicio"][11:16]) == ("Centro Cultural Terminal Goes", -34.882708, "16:00")
    # "📍 Modalidad presencial o virtual" no es un lugar: queda el de la cuenta.
    fac = {"usuario": "facmvd", "nombre": "FAC", "direccion": "Av. Sarmiento 2244"}
    (d,) = ig.borradores_del_post(_post(3, "Sábado 14 de noviembre\n🕕 De 11 a 13 h\n📍 Modalidad presencial o virtual",
                                        "2026-11-05"), fac, {}, AHORA)
    assert (d["lugar"], d["direccion"]) == ("FAC", "Av. Sarmiento 2244")


def test_el_punto_de_encuentro_y_el_mismo_bar_con_otras_palabras(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    (tmp_path / "bares.toml").write_text(
        '[[bar]]\nusuario = "fenixbaruy"\nnombre = "Fénix Bar"\ndireccion = "Juan Carlos Gómez 1251"\n', encoding="utf-8")
    # En un recorrido, el 📍 es el nombre de la actividad: el lugar es el punto de encuentro.
    fama = {"usuario": "fama.tours", "itinerante": True, "bar": False}
    (b,) = ig.borradores_del_post(_post(1, "Volvemos a un reconocimiento arquitectónico.\n\n📍 Caminata Art Nouveau \n\n"
                                        "📅 Sábado 21 de Noviembre de 2026 \n🕜 12:00 a 13:30 horas\n\n"
                                        "👉 Punto de encuentro: Bacacay y Buenos Aires\n\n👉 Itinerario", "2026-11-12"),
                                  fama, {}, AHORA)
    assert (b["lugar"], b["funciones"][0]["inicio"][:16]) == ("Bacacay y Buenos Aires", "2026-11-21T12:00")
    # "📍 Bar Fénix" en la cuenta de "Fénix Bar" es el mismo bar, con su dirección y la etiqueta.
    fenix = {"usuario": "fenixbaruy", "nombre": "Fénix Bar", "direccion": "Juan Carlos Gómez 1251"}
    (c,) = ig.borradores_del_post(_post(2, "Jueves 26 de noviembre, 20:30 h\n📍 Bar Fénix", "2026-11-12"), fenix, {}, AHORA)
    assert (c["lugar"], c["direccion"], c["bar"], c["lugar_del_pin"]) == ("Fénix Bar", "Juan Carlos Gómez 1251", True, False)


def test_las_paradas_de_un_recorrido():
    oro = ("📍Oro en los Salones. Reconocimiento estilístico de los interiores de Quinta de Mendilaharsu (Museo de "
           "Antropología), Foyer del Teatro Solís, Palacio Taranco (Museo de Artes Decorativas) y Palacete Beatriz. "
           "Merienda. \n\n📅 Sábado 14 de Noviembre - 14:00 hs")
    assert ig.paradas_del_recorrido(oro)[:3] == ["Quinta de Mendilaharsu", "Museo de Antropología", "Foyer del Teatro Solís"]
    caminata = ("📍 Caminata Art Nouveau\n\n👉 Itinerario \n*Edificio Tienda La Nueva Sirena \n*Casa Mojana (Centro "
                "Cultural de España)\n\n📍Actividad sin costo")
    assert ig.paradas_del_recorrido(caminata) == ["Edificio Tienda La Nueva Sirena", "Casa Mojana", "Centro Cultural de España"]
    assert ig.paradas_del_recorrido("📍 MBC Ombú\nViernes 20 h") == []


def test_la_categoria_de_la_cuenta():
    fama = {"usuario": "fama.tours", "itinerante": True, "bar": False, "categoria": "tour"}
    (b,) = ig.borradores_del_post(_post(1, "📍Oro en los Salones. Reconocimiento de Quinta de Mendilaharsu, Foyer del "
                                        "Teatro Solís y Palacete Beatriz.\n\n📅 Sábado 21 de Noviembre - 14:00 hs", "2026-11-12"),
                                  fama, {}, AHORA)
    evento = ig.evento_de({**b, "aprobado": True}, AHORA)
    assert (evento.categoria, evento.lugar.alternativas[0]) == ("tour", "Quinta de Mendilaharsu")


def test_el_tipo_por_defecto_de_un_bar_de_musica(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "el.mingus"\npor_defecto = "musica"\n', encoding="utf-8")
    mingus = {"usuario": "el.mingus", "direccion": "San Salvador 1952"}
    (b,) = ig.borradores_del_post(_post(1, "Jazzterday\nJueves 26 de noviembre, 21 h", "2026-11-12"), mingus, {}, AHORA)
    assert ig.evento_de({**b, "aprobado": True}, AHORA).categoria == "musica"
    # Si el post dice qué es, manda el post.
    (c,) = ig.borradores_del_post(_post(2, "Noche de stand up\nViernes 27 de noviembre, 21 h", "2026-11-12"), mingus, {}, AHORA)
    assert ig.evento_de({**c, "aprobado": True}, AHORA).categoria == "humor"
    # Otra cuenta, sin tipo por defecto, sigue en "otros".
    (d,) = ig.borradores_del_post(_post(3, "Jazzterday\nJueves 26 de noviembre, 21 h", "2026-11-12"),
                                  {"usuario": "cordonbeer"}, {}, AHORA)
    assert ig.evento_de({**d, "aprobado": True}, AHORA).categoria == "otros"


def test_una_correccion_a_mano_cambia_el_lugar_de_esa_fecha(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    (tmp_path / "bares.toml").write_text(
        '[[bar]]\nusuario = "mambapercusion"\nitinerante = true\nbar = false\n\n'
        '[[correccion]]\nid = "mambapercusion-20261205"\nlugar = "Plaza Viejo Pancho"\nlat = -34.910003\nlon = -56.1576635\n'
        'notas = "en el afiche"\n', encoding="utf-8")
    mamba = {"usuario": "mambapercusion", "itinerante": True, "bar": False}
    (b,) = ig.borradores_del_post(_post(1, "El 5 de diciembre a las 20 h nos encontramos en el lugar de siempre", "2026-11-12"),
                                  mamba, {}, AHORA)
    evento = ig.evento_de({**b, "aprobado": True}, AHORA)
    assert (evento.lugar.nombre, evento.lugar.lat, evento.lugar.lon) == ("Plaza Viejo Pancho", -34.910003, -56.1576635)
    # Otra fecha de la misma cuenta no cambia.
    (c,) = ig.borradores_del_post(_post(2, "El 12 de diciembre a las 20 h, fiesta", "2026-11-12"), mamba, {}, AHORA)
    assert ig.evento_de({**c, "aprobado": True}, AHORA).lugar.lat is None


def test_fecha_con_punto_y_sin_la_de_las_entradas():
    texto = ("El 14.11 (mañana) largamos la primer tanda de entradas a $400!\n\nGuardate el 12.12!\n@kumbiaracha\n\n"
             "En Sala Rincón")
    publicado = datetime(2026, 11, 13, 12, 0, tzinfo=MVD)
    (b,) = ig.borradores_del_post(_post(1, texto, "2026-11-13"), {"usuario": "andromedabarcoop", "direccion": "Durazno 1100"},
                                  {"name": "Andrómeda"}, publicado)
    assert [f["inicio"][:10] for f in b["funciones"]] == ["2026-12-12"]
    assert b["lugar"] == "Sala Rincón"
    # Una hora o un precio con punto no son una fecha.
    assert ig.fechas_explicitas("a las 21.10 hs, entrada $1.200", publicado.date()) == []


def test_un_pin_con_otra_direccion_es_otro_lugar():
    cuenta = {"usuario": "contraplano.cineclub", "nombre": "Contraplano Cineclub", "direccion": "Ecuador 1680", "bar": False}
    otro = "Vemos HER\n28 de noviembre\n20 hs\n📍 Maciel 1384, Ciudad Vieja"
    (b,) = ig.borradores_del_post(_post(1, otro, "2026-11-09"), cuenta, {}, AHORA)
    assert (b["lugar"], b["direccion"]) == ("Maciel 1384", "Maciel 1384")
    propio = "Vemos El laberinto del fauno\n28 de noviembre\n17 hs\n📍 Ecuador 1680, Villa del Cerro"
    (c,) = ig.borradores_del_post(_post(2, propio, "2026-11-09"), cuenta, {}, AHORA)
    assert (c["lugar"], c["direccion"]) == ("Contraplano Cineclub", "Ecuador 1680")


def test_un_pin_que_es_una_esquina_es_la_direccion():
    assert ig.lugar_del_texto("📍 Aquiles Lanza y Canelones.\n🕛 Desde las 12:00 h.") == (None, "Aquiles Lanza y Canelones")
    bar = {"usuario": "elbar_delxsamigxs"}
    (b,) = ig.borradores_del_post(_post(1, "Este 29 de noviembre nos encontramos en la calle\n📍 Aquiles Lanza y Canelones.\n"
                                        "🕛 Desde las 12:00 h.", "2026-11-12"), bar, {"name": "Brecha Bar y Cafe"}, AHORA)
    assert (b["lugar"], b["direccion"]) == ("Brecha Bar y Cafe", "Aquiles Lanza y Canelones")


def test_un_recorrido_sin_paradas_va_al_barrio_que_recorre():
    fama = ("📍Carrasco y Bodega.\n\n👉 Caminata por Carrasco viejo, con la participación de Arq. Beatriz Pittamiglio. "
            "Visita guiada a viñedos de Bodega Varela Zarranz.")
    assert ig.paradas_del_recorrido(fama) == ["Carrasco"]
    assert ig.paradas_del_recorrido("Paseo por Ciudad Vieja, sábado 10 h") == ["Ciudad Vieja"]


def test_una_fecha_con_anio_pasado_no_es_un_evento():
    texto = "Pamela presentó por primera vez Lluvias en el teatrosolis el 2 de diciembre de 2025.\nLa cita es esta noche."
    assert ig.borradores_del_post(_post(1, texto, "2026-11-04"), {"usuario": "paseo"}, {}, AHORA) == []
    assert ig.fechas_explicitas("2 de diciembre de 2026", AHORA.date()) == [(date(2026, 12, 2), True)]


def test_el_lugar_tambien_con_otros_iconos():
    assert ig.lugar_del_texto("🗓️ 24 de noviembre\n🕖 20 H\n🏛️Auditorio Vaz Ferreira\n🎟️Entradas") == ("Auditorio Vaz Ferreira", None)
    assert ig.lugar_del_texto("📌 Sala Hugo Balzo") == ("Sala Hugo Balzo", None)


def test_un_icono_de_lugar_que_marca_la_fecha_no_es_el_lugar():
    texto = "TABAREK & LA KABARET\n\n📌SÁBADO 21 DE NOV\n🕘 21 H"
    assert ig.lugar_del_texto(texto) == (None, None)
    assert ig.lugar_del_texto("📌 Jueves 26\n📍 Sala Hugo Balzo") == ("Sala Hugo Balzo", None)


def test_el_pin_con_la_direccion_entre_parentesis():
    assert ig.lugar_del_texto("📍 CCE (Rincón 629)") == ("CCE", "Rincón 629")


def test_un_pin_con_el_dia_abreviado_no_es_el_lugar():
    # La agenda del aniversario de Charco: "📌 Jue. 19.11 · 18:30 — …" es la fecha, no dónde.
    texto = ("ACTIVIDADES:\n\n📌 Jue. 19.11 · 18:30 — Leila Guerriero conversa con Soledad Gago.\n\n"
             "📌 Vie 20.11 · 13:00 — Conferencia en la FIC.\n\n📌 19.11 · 20:00 — Brindis.")
    assert ig.lugar_del_texto(texto) == (None, None)
    assert ig.lugar_del_texto("📌 Jue. 19.11\n📍 Maldonado 1477") == (None, "Maldonado 1477")
    # Un lugar que empieza con esas letras sigue siendo un lugar.
    assert ig.lugar_del_texto("📍 Mar Chiquita, Rambla 1234") == ("Mar Chiquita", "Rambla 1234")


def test_una_correccion_a_mano_cambia_el_titulo_y_el_dia(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    (tmp_path / "bares.toml").write_text(
        '[[bar]]\nusuario = "azotealee"\nitinerante = true\nbar = false\n\n'
        '[[correccion]]\nid = "azotealee-20261129"\ntitulo = "Lecturas de azotea: Silvio en la azotea"\n'
        'inicio = "2026-11-28T19:00:00-03:00"\n', encoding="utf-8")
    cuenta = {"usuario": "azotealee", "itinerante": True, "bar": False}
    (b,) = ig.borradores_del_post(_post(1, "El domingo 29 Silvio cumple 80 y nosotros lo festejamos el día antes.", "2026-11-18"),
                                  cuenta, {}, AHORA)
    assert b["id"] == "azotealee-20261129"
    evento = ig.evento_de({**b, "aprobado": True, "titulo_aprobado": "Lecturas de azotea: Silvio cumple 80"}, AHORA)
    assert evento.titulo == "Lecturas de azotea: Silvio en la azotea"
    assert [(f.inicio.isoformat(), f.sin_hora) for f in evento.funciones] == [("2026-11-28T19:00:00-03:00", False)]
    # Corregir solo el título no le saca la dirección a un lugar fijo.
    (tmp_path / "bares.toml").write_text(
        '[[bar]]\nusuario = "clubculturalcharco"\nnombre = "Charco"\ndireccion = "Maldonado 1477"\n\n'
        '[[correccion]]\nid = "clubculturalcharco-20261127"\ntitulo = "Charco: Pianobar"\n', encoding="utf-8")
    charco = {"usuario": "clubculturalcharco", "nombre": "Charco", "direccion": "Maldonado 1477"}
    (c,) = ig.borradores_del_post(_post(2, "Viernes 27 de noviembre a las 20:30, pianobar", "2026-11-18"), charco, {}, AHORA)
    evento = ig.evento_de({**c, "aprobado": True}, AHORA)
    assert (evento.titulo, evento.lugar.nombre, evento.lugar.direccion) == ("Charco: Pianobar", "Charco", "Maldonado 1477")


def test_dos_eventos_el_mismo_dia_en_lugares_distintos_no_se_juntan():
    cuenta = {"usuario": "cultus_uy", "nombre": "Casa Cultus", "direccion": "Piedras 604", "bar": False}
    ahora = datetime(2026, 11, 19, 9, 0, tzinfo=MVD)
    muestra = ("«Entre aquí y allá»\nHuellas de la diáspora\n\nUna exposición y cuatro encuentros con los artistas.\n\n"
               "📍 Casa Cultus, Piedras 604\n🗓️ Sábado 21 de noviembre, de 12:00 a 20:30 h\nEntrada libre y gratuita")
    afuera = "Sábados en Ciudad Vieja · El Bajo se encuentra\n📍 Patio La Bahía\nSábado 21 de noviembre, 17 h"
    otra_vez = "El Bajo se encuentra, este sábado 21 de noviembre a las 17 h. ¡Los esperamos!"
    (a,) = ig.borradores_del_post(_post(1, afuera, "2026-11-17"), cuenta, {}, ahora)
    (b,) = ig.borradores_del_post(_post(2, muestra, "2026-11-19"), cuenta, {}, ahora)
    (c,) = ig.borradores_del_post(_post(3, otra_vez, "2026-11-18"), cuenta, {}, ahora)
    assert a["id"] == b["id"] == c["id"] == "cultus_uy-20261121"
    # En cualquier orden: la muestra (en la casa) con el identificador de siempre y lo de afuera con su lugar.
    for orden in ([a, b, c], [b, a, c], [c, a, b], [b, c, a]):
        corrida = {}
        for nuevo in orden:
            ig.sumar(corrida, nuevo)
        corrida = ig.juntar_parecidos(corrida)
        assert sorted(corrida) == ["cultus_uy-20261121", "cultus_uy-20261121-patio-la-bahia"]
        assert corrida["cultus_uy-20261121"]["lugar"] == "Casa Cultus"
        assert corrida["cultus_uy-20261121"]["titulo"] == "Casa Cultus: Entre aquí y allá"
        assert corrida["cultus_uy-20261121-patio-la-bahia"]["lugar"] == "Patio La Bahía"
    # Un post sin 📍 se junta con el que lo dice, como siempre (el mismo evento anunciado dos veces).
    assert len(corrida["cultus_uy-20261121"]["posts"]) + len(corrida["cultus_uy-20261121-patio-la-bahia"]["posts"]) == 3


def test_la_direccion_que_falta_se_escribe_en_el_aviso():
    b = {"id": "cultus_uy-20261121-patio-la-bahia", "usuario": "cultus_uy", "titulo": "Casa Cultus: El Bajo se encuentra",
         "lugar": "Patio La Bahía", "direccion": None, "lat": None, "lon": None, "texto": "El Bajo se encuentra",
         "funciones": [{"inicio": "2026-11-21T17:00:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/1/"}
    ahora = datetime(2026, 11, 19, 9, 0, tzinfo=MVD)
    renglon = ig.renglon_del_borrador(b, ahora)
    assert "📍 Patio La Bahía · ⚠️ **AGREGAR DIRECCIÓN**" in renglon
    assert ig.direcciones_del_aviso([renglon]) == {}  # sin tocar, no hay dirección
    otro = ig.renglon_del_borrador({**b, "id": "otro-1", "lugar": "Bar", "direccion": "Soriano 1236"}, ahora)
    editado = renglon.replace("- [ ]", "- [x]").replace("AGREGAR DIRECCIÓN", "Piedras 450") + "\n" + otro
    assert ig.direcciones_del_aviso([editado]) == {b["id"]: "Piedras 450"}
    assert ig.leer_casillas([editado])[0] == {b["id"]: "Casa Cultus: El Bajo se encuentra"}
    evento = ig.evento_de({**b, "aprobado": True, "direccion_aprobada": "Piedras 450"}, ahora)
    assert (evento.lugar.nombre, evento.lugar.direccion) == ("Patio La Bahía", "Piedras 450")


def test_la_fecha_con_barra_al_principio_no_queda_en_el_titulo():
    texto = ("Este jueves 26/11 Garo Arakelian vuelve al Bar Andorra para interpretar las canciones de su discografía "
             "solista (Un Mundo Sin Gloria y Milonga de Quirón).\n21:30hs\nEntrada libre")
    titulo = ig.titulo_de(texto, "Bar Andorra")
    assert titulo.startswith("Garo Arakelian vuelve al Bar Andorra")
    assert ig.titulo_de("Viernes 4.12 Noche de tango", "Bar").startswith("Noche de tango")


def test_lo_aprobado_que_se_conserva_se_junta_con_el_post_del_dia(tmp_path, monkeypatch):
    # El post del ciclo ("Próximo recital: 25 de noviembre"), aprobado y ya fuera de los últimos posts, y el post del 25.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "ccemontevideo"\nnombre = "Centro Cultural de España"\nbar = false\n')
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "x")
    ciclo = {"id": "ccemontevideo-20261111", "usuario": "ccemontevideo", "titulo": "Centro Cultural de España: Beethoven 199",
             "lugar": "Centro Cultural de España", "texto": "Beethoven 199", "aprobado": True,
             "titulo_aprobado": "Centro Cultural de España: Beethoven 199",
             "funciones": [{"inicio": "2026-11-11T19:00:00-03:00", "sin_hora": False},
                           {"inicio": "2026-11-25T19:00:00-03:00", "sin_hora": False}],
             "url": "https://www.instagram.com/p/1/", "posts": ["https://www.instagram.com/p/1/"], "publicado": "2026-11-05T12:00:00-03:00"}
    ig.guardar_borradores({ciclo["id"]: ciclo})
    del_dia = {"id": "2", "caption": "¡Beethoven 199! La música de cámara llega al CCE.\n📅 miércoles 25 de noviembre\n🕖 19:00 h",
               "media_type": "IMAGE", "media_url": "https://cdn/2.jpg", "permalink": "https://www.instagram.com/p/2/",
               "timestamp": "2026-11-09T15:00:00+0000"}
    monkeypatch.setattr(ig, "TRANSPORTE", httpx.MockTransport(lambda pedido: httpx.Response(200, json=(
        {"instagram_business_account": {"id": "1"}} if pedido.url.path.endswith("/me")
        else {"business_discovery": {"name": "CCE", "media": {"data": [del_dia]}}}))))
    monkeypatch.setattr(ig, "avisos_en_github", lambda: None)
    eventos, _ = ig.scrapear(None, AHORA)
    assert list(ig.cargar_borradores()) == ["ccemontevideo-20261111"]
    (evento,) = eventos
    assert evento.titulo == "Centro Cultural de España: Beethoven 199" and len(ig.cargar_borradores()["ccemontevideo-20261111"]["posts"]) == 2


PEATONAL_BELLO = """🏛️ ᴘᴀꜱᴇᴏ ʙᴇʟʟᴏ & ʀᴇʙᴏʀᴀᴛɪ ᴘᴏʀ ᴘᴏᴄɪᴛᴏꜱ

🗣️ Los invitamos a redescubrir la huella de B&R en un recorrido.

▪️ Plaza Gomensoro
▫️ Casa de Ramón Bello

 🗓️ Domingo 29/11 - 15hs.
📍 Desde la Plaza Gomensoro (sobre Benito Blanco).
💲$500 por persona.
#pocitos #peatonaltours"""

PEATONAL_PATRIMONIAL = """ᴛᴏᴜʀ ᴘᴀᴛʀɪᴍᴏɴɪᴀʟ ʏ ᴀʀǫᴜɪᴛᴇᴄᴛóɴɪᴄᴏ 🏛️

🗣️ Como cierre de año de Paseo Centro y en el marco de la Feria, realizaremos un recorrido.

 🗓️ Domingo 06/12 - 11hs.
💲 GRATUITO.
📍 desde Plaza Cagancha (fotogalería).

🇺🇾 Finalizamos en Club Cultural Charco (clubculturalcharco )."""

PEATONAL_AGENDA = """En Noviembre quedan los siguientes tours para salir a pasear con Peatonal:

Jueves 26 - 20hs: Misterios del Salvo
Las entradas se adquieren por la web de Redtickets

Sábado 28 - 11hs: Tour religioso por Ciudad Vieja
Entradas por nuestra web peatonaltours.uy

Domingo 29 - 15hs: Paseo Bello & Reborati
Entradas por nuestra web peatonaltours.uy"""


def test_los_posts_de_peatonal_tours():
    cuenta = {"usuario": "peatonaltours", "nombre": "Peatonal Tours", "itinerante": True, "categoria": "tour", "bar": False}
    ahora = datetime(2026, 11, 23, 12, 0, tzinfo=MVD)
    # Las versalitas se leen como letras comunes; el 🏛️ del título no es el lugar; "desde la" y la aclaración entre
    # paréntesis sobran; y en "29/11 - 15hs" la hora es 15, no el mes.
    [bello] = ig.borradores_del_post(_post(1, PEATONAL_BELLO, "2026-11-20"), cuenta, {}, ahora)
    assert (bello["titulo"], bello["lugar"], bello["funciones"]) == (
        "Peatonal Tours: PASEO BELLO & REBORATI POR POCITOS", "Plaza Gomensoro",
        [{"inicio": "2026-11-29T15:00:00-03:00", "sin_hora": False}])
    # Un 🏛️ al final del renglón no toma el renglón de abajo, y el lugar no es el del final del recorrido.
    [patrimonial] = ig.borradores_del_post(_post(2, PEATONAL_PATRIMONIAL, "2026-11-20"), cuenta, {}, ahora)
    assert (patrimonial["titulo"], patrimonial["lugar"], patrimonial["funciones"][0]["inicio"]) == (
        "Peatonal Tours: TOUR PATRIMONIAL Y ARQUITECTÓNICO", "Plaza Cagancha", "2026-12-06T11:00:00-03:00")
    # "Jueves 26 - 20hs: Misterios del Salvo": a las 20, y el nombre es lo de después de la hora.
    agenda = ig.borradores_del_post(_post(3, PEATONAL_AGENDA, "2026-11-20"), cuenta, {}, ahora)
    assert [(b["titulo"], b["funciones"][0]["inicio"][5:16]) for b in agenda] == [
        ("Peatonal Tours: Misterios del Salvo", "11-26T20:00"), ("Peatonal Tours: Tour religioso por Ciudad Vieja", "11-28T11:00"),
        ("Peatonal Tours: Paseo Bello & Reborati", "11-29T15:00")]


def test_letras_de_adorno():
    assert ig.letras_comunes("𝗠𝗜𝗦𝗧𝗘𝗥𝗜𝗢𝗦 𝗗𝗘𝗟 𝗦𝗔𝗟𝗩𝗢 · ᴇᴅɪᴄɪóɴ 2026 · 1º") == "MISTERIOS DEL SALVO · EDICIÓN 2026 · 1º"
    assert ig.horas("18.30 a 20.30 hs") == [ig.time(18, 30)] and ig.horas("Dom 29/11 - 15hs") == [ig.time(15, 0)]
