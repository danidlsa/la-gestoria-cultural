"""Modelo de datos de la cartelera (ver docs/diseno.md)."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, field_validator

def _solo_web(url: str) -> str:
    """Los enlaces que vienen de las fuentes terminan en la web: solo http(s), nunca `javascript:` y similares."""
    if not url.strip().lower().startswith(("https://", "http://")):
        raise ValueError(f"enlace que no es web: {url[:60]!r}")
    return url.strip()


def _imagen_web(url: str | None) -> str | None:
    """Una imagen con un enlace raro se descarta sin descartar el evento."""
    return url.strip() if url and url.strip().lower().startswith(("https://", "http://")) else None


UrlWeb = Annotated[str, AfterValidator(_solo_web)]
ImagenWeb = Annotated[str | None, AfterValidator(_imagen_web)]

Categoria = Literal[
    "musica", "teatro", "danza", "humor", "cine", "exposicion", "infantil",
    "fiesta", "festival", "carnaval", "tour", "charla", "taller", "otros",
]
Region = Literal["montevideo", "buenos_aires"]


class Funcion(BaseModel):
    inicio: datetime
    fin: datetime | None = None  # pocas fuentes lo informan (el Sodre sí)
    sin_hora: bool = False  # la fuente da solo el día; `inicio` queda a las 00:00
    sala: str | None = None
    agotada: bool = False

    @field_validator("inicio")
    @classmethod
    def con_zona_horaria(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None:
            raise ValueError("la fecha de la función tiene que tener zona horaria")
        return valor


class Precio(BaseModel):
    desde: float | None = None
    hasta: float | None = None
    moneda: str = "UYU"
    gratis: bool = False


class Entrada(BaseModel):
    url: UrlWeb
    via: str


class Beneficio(BaseModel):
    programa: str
    tipo: str
    url: UrlWeb


class Procedencia(BaseModel):
    fuente: str
    id_externo: str
    url: UrlWeb
    visto: datetime


class LugarCrudo(BaseModel):
    """El lugar tal como lo describe una fuente, antes de cruzarlo con el catálogo."""

    nombre: str
    direccion: str | None = None
    lat: float | None = None
    lon: float | None = None
    barrio: str | None = None  # pocas fuentes lo dicen (el mapa de la Noche de las Librerías sí)


class EventoCrudo(BaseModel):
    """Lo que produce un scraper: un evento visto desde una sola fuente."""

    fuente: str
    id_externo: str
    url: UrlWeb
    titulo: str
    categoria: Categoria = "otros"
    categoria_segura: bool = False  # True si la categoría viene de la fuente y no de palabras clave
    descripcion_corta: str | None = None
    lugar: LugarCrudo
    funciones: list[Funcion]
    precio: Precio | None = None
    entradas: list[Entrada] = []
    beneficios: list[Beneficio] = []
    imagen_url: ImagenWeb = None
    productor: str | None = None
    region: Region = "montevideo"
    # Enlaces a eventos de otras fuentes (por ejemplo, a RedTickets), para deduplicar de forma exacta.
    enlaces: list[str] = []
    ciclo: str | None = None  # nombre del ciclo, cuando la fuente lo informa (Cinemateca)
    # Etiquetas que da la fuente: "bar" (los bares de Instagram). Se suman a las que se detectan al unificar.
    etiquetas: list[str] = []
    # Una exposición: se muestra con su período ("Hasta el 28 feb") y no como una función por día.
    muestra: bool = False
    hasta: date | None = None  # cierre de la exposición, si la fuente lo informa


class ResultadoFuente(BaseModel):
    """Contenido de datos/fuentes/<fuente>.json."""

    fuente: str
    corrida: datetime
    ok: bool
    cantidad: int
    errores: list[str] = []
    eventos: list[EventoCrudo]


class Lugar(BaseModel):
    id: str
    nombre: str
    alias: list[str] = []
    direccion: str | None = None
    lat: float | None = None
    lon: float | None = None
    barrio: str | None = None
    ciudad: str = "Montevideo"


Subcategoria = Literal[
    "comedia_nacional", "ballet_sodre", "stand_up", "cinemateca",
    "clasica", "tropical", "rock_pop",  # géneros gruesos de la música
]


class Ciclo(BaseModel):
    """Una serie de eventos relacionados: un ciclo de una sala, una temporada, un festival con varias fechas."""

    id: str
    titulo: str
    lugar_id: str | None = None
    desde: datetime
    hasta: datetime
    cantidad: int


class Evento(BaseModel):
    """Un evento de la cartelera unificada (datos/eventos.json)."""

    id: str
    titulo: str
    categoria: Categoria
    subcategoria: Subcategoria | None = None
    etiquetas: list[str] = []  # "festival", "museo", "bar"
    descripcion_corta: str | None = None
    lugar_id: str
    ciclo_id: str | None = None
    ciclo_nombre: str | None = None  # el que informa la fuente; si no hay, se detecta por el título
    muestra: bool = False
    hasta: date | None = None
    funciones: list[Funcion]
    precio: Precio | None = None
    entradas: list[Entrada] = []
    beneficios: list[Beneficio] = []
    imagen_url: ImagenWeb = None
    productor: str | None = None
    region: Region = "montevideo"
    fuentes: list[Procedencia]
    actualizado: datetime
