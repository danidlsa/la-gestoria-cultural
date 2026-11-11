"""Filtro geográfico: la cartelera es solo de Montevideo.

Se decide por coordenadas y no por texto: muchas calles de Montevideo se llaman
como departamentos (Colonia, Mercedes, Canelones, Paysandú), así que buscar
nombres de localidades en la dirección daría falsos positivos.
"""

import re
import unicodedata

# Caja aproximada del departamento de Montevideo.
LAT_MIN, LAT_MAX = -34.94, -34.70
LON_MIN, LON_MAX = -56.43, -56.02


# Lugar de las actividades municipales que se hacen en muchos barrios a la vez (ver scrapers/portal_im.py).
# En el mapa va en la Intendencia (config/lugares_alias.toml).
VARIOS_BARRIOS = "Varios barrios de Montevideo"


def sin_tildes(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normal if not unicodedata.combining(c)).lower()


def en_montevideo(lat: float | None, lon: float | None) -> bool:
    """True si el punto cae en Montevideo. Sin coordenadas no se puede descartar."""
    if lat is None or lon is None:
        return True
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return False
    # Las Piedras y La Paz (Canelones) quedan dentro de la caja, al norte.
    if -56.27 <= lon <= -56.15 and lat > -34.775:
        return False
    # Paso Carrasco y el aeropuerto (Canelones), al noreste del arroyo Carrasco.
    if lon > -56.06 and lat > -34.875:
        return False
    # Toledo y alrededores (Canelones), al norte de Punta de Rieles.
    if -56.15 < lon <= -56.06 and lat > -34.78:
        return False
    return True


# Un texto que termina en otro departamento: "No Te Va Gustar en Salto", "Harlem Globetrotters – Durazno",
# "Cardal Florida". Solo al final: en el medio, muchas calles de Montevideo se llaman así (Colonia, Paysandú).
_OTRA_CIUDAD = re.compile(
    r"(?:\ben\b|[–,-]|\s)\s*(artigas|canelones|cerro largo|colonia|durazno|flores|florida|lavalleja|maldonado|"
    r"punta del este|paysandu|rio negro|rivera|rocha|salto|san jose|soriano|tacuarembo|treinta y tres)\s*\.?$"
)


# Pero una esquina o una sala con ese nombre es de Montevideo: "Gutiérrez Ruiz 1111 esq. Durazno", "Auditorio San
# José", "Soriano y Colonia".
_CALLE_O_SALA = re.compile(
    r"\b(esq\.?|esquina|y|e/|entre|auditorio|sala|calle|av\.?|avenida|bv\.?|bulevar|plaza|pasaje|edificio)\s+"
    r"(artigas|canelones|cerro largo|colonia|durazno|flores|florida|lavalleja|maldonado|punta del este|paysandu|"
    r"rio negro|rivera|rocha|salto|san jose|soriano|tacuarembo|treinta y tres)\s*\.?$"
)


def menciona_otra_ciudad(texto: str) -> bool:
    plano = sin_tildes(texto.strip())
    return bool(_OTRA_CIUDAD.search(plano)) and not _CALLE_O_SALA.search(plano)

