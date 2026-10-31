"""Promociones y beneficios a partir del nombre de una entrada ("2x1 La Diaria", "50% OFF Socio El Galpón")."""

import re

from cartelera.modelo import Beneficio

# Programas de beneficios reconocibles en el nombre de la entrada (tolera errores de tipeo frecuentes).
_PROGRAMAS = [
    ("la diaria", re.compile(r"\b(la ?)?di(a|ra)ria\b", re.I)),
    ("Socio Espectacular", re.compile(r"espectacular", re.I)),
    ("Club El País", re.compile(r"\bel pa[ií]s\b", re.I)),
    ("BROU", re.compile(r"\bbrou\b", re.I)),
    ("Itaú", re.compile(r"\bita[uú]\b", re.I)),
    ("Santander", re.compile(r"\bsantander\b", re.I)),
    ("Scotiabank", re.compile(r"\bscotia", re.I)),
    ("BBVA", re.compile(r"\bbbva\b", re.I)),
    ("OCA", re.compile(r"\boca\b", re.I)),
    ("HSBC", re.compile(r"\bhsbc\b", re.I)),
    ("Futurock", re.compile(r"\bfuturock\b", re.I)),
    ("AEBU", re.compile(r"\baebu\b", re.I)),
    ("Alianza Francesa", re.compile(r"\balianza\b", re.I)),
]
# Nunca son promociones.
_NO_PROMO = re.compile(r"cortes|invitac|acredit|producci[oó]n|prensa", re.I)
# Tarifas o tipos de entrada comunes: no son promociones salvo que nombren un programa conocido.
_TARIFA = re.compile(
    r"\bsua\b|montevideo libre|menor|jubilad|estudiant|ni[nñ]o|discapac|pre ?venta|anticipad|"
    r"agotar|limitad|abono|\bpase\b|tanda|pista|sentad|de pie|platea|palco|combo|escucha|general",
    re.I,
)
_PROMO = re.compile(r"\d ?x ?\d|\bx ?2\b|\d+ ?% ?(off|dto|desc)?|descuento|promo|\bd[uú]o\b", re.I)
_GRUPAL = re.compile(r"\b[3-9] ?x ?\d\b|\bx ?2\b|\b\d\s*x\s*\$|\bd[uú]o\b|pareja|amigos|grupal", re.I)
_SOCIOS = re.compile(r"\bsocios? (?:de(?:l)? )?(?P<club>[^-–(/]+)", re.I)
_RELLENO_CLUB = re.compile(r"\d+ ?%|\b(\d ?x ?\d|off|c/?u|silla|activos?|precio|final)\b", re.I)


def club_de_socios(nombre: str) -> str | None:
    """'50% OFF Socio El Galpón - Platea A' -> 'El Galpón'; 'Socio Activo (Precio Final)' -> None."""
    encontrado = _SOCIOS.search(nombre)
    if not encontrado:
        return None
    club = re.sub(r"\s+", " ", _RELLENO_CLUB.sub(" ", encontrado.group("club"))).strip(" .")
    club = re.sub(r"\s+c$", "", club, flags=re.I)  # resto de "c/u"
    if len(club) < 3:
        return None
    return club if club.isupper() and len(club) <= 6 else club[:1].upper() + club[1:]


def programa(nombre: str) -> str | None:
    """De qué programa es una entrada promocional ("2x1 La Diaria c/u" -> "la diaria")."""
    if _NO_PROMO.search(nombre):
        return None
    for programa, patron in _PROGRAMAS:
        if patron.search(nombre):
            return programa
    if re.search(r"\bsocios?\b", nombre, re.I):
        club = club_de_socios(nombre)
        return f"Socios {club}" if club else "Socios de la sala"
    if _TARIFA.search(nombre) or not _PROMO.search(nombre):
        return None
    if _GRUPAL.search(nombre):
        return "Promo grupal"
    # Un 2x1 que no nombra a nadie es para todos; si nombra algo desconocido, tiene condiciones.
    resto = re.sub(r"\s+", " ", re.sub(r"\d ?x ?\d|promo\w*|c/?u|[^\w ]", " ", nombre, flags=re.I)).strip()
    if re.search(r"\d ?x ?\d", nombre, re.I) and not resto:
        return "2x1 para todos"
    return "Otras promos"


def programas(nombre: str) -> list[str]:
    """Todos los programas que nombra una entrada: "BROU y La Diaria 2x1" -> ["la diaria", "BROU"]."""
    if _NO_PROMO.search(nombre):
        return []
    conocidos = [p for p, patron in _PROGRAMAS if patron.search(nombre)]
    if conocidos:
        return conocidos
    unico = programa(nombre)
    return [unico] if unico else []


def beneficios_de_entradas(entradas: list[str], url: str) -> list[Beneficio]:
    """Un beneficio por programa, con los nombres de sus tipos de entrada ("2x1" se resume)."""
    tipos: dict[str, list[str]] = {}
    for nombre in dict.fromkeys(n.strip() for n in entradas):
        for de_programa in programas(nombre):
            tipos.setdefault(de_programa, []).append("2x1" if re.search(r"2 ?x ?1", nombre, re.I) else nombre)
    return [Beneficio(programa=p, tipo=", ".join(dict.fromkeys(t)), url=url) for p, t in tipos.items()]
