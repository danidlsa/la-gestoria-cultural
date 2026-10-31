"""Lo común a los museos: exposiciones con un período (o "actuales", sin fecha de cierre) y fechas en texto."""

import re
from datetime import date, datetime, time, timedelta

from cartelera.geo import sin_tildes
from cartelera.modelo import Funcion

# Una exposición se carga como una función "sin hora" por día, hasta este horizonte: así aparece en la
# agenda de cada día y en "Ver propuestas con muchas fechas", sin cargar meses de días.
DIAS_ADELANTE = 60
# Las exposiciones "actuales" sin fecha de cierre se dan por abiertas este tiempo; cada corrida lo renueva.
DIAS_SIN_CIERRE = 30
MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "sep": 9,
    "oct": 10, "nov": 11, "dic": 12,
}


def mes_de(nombre: str) -> int | None:
    return MESES.get(sin_tildes(nombre)[:3])


def funciones_de_muestra(desde: date | None, hasta: date | None, ahora: datetime) -> list[Funcion]:
    """Un día "sin hora" por cada día abierto entre hoy (o la inauguración) y el cierre (o el horizonte)."""
    hoy = ahora.date()
    inicio = max(desde or hoy, hoy)
    fin = min(hasta or hoy + timedelta(days=DIAS_SIN_CIERRE), hoy + timedelta(days=DIAS_ADELANTE))
    dias = (fin - inicio).days + 1
    return [
        Funcion(inicio=datetime.combine(inicio + timedelta(days=n), time(0, 0), tzinfo=ahora.tzinfo), sin_hora=True)
        for n in range(max(dias, 0))
    ]


def ultimo_dia_del_mes(anio: int, mes: int) -> date:
    siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
    return siguiente - timedelta(days=1)


def periodo_por_meses(texto: str) -> tuple[date, date] | None:
    """'Abril 2026 - Abril 2027' o 'Agosto - Noviembre 2026' -> (1 de abril de 2026, 30 de abril de 2027)."""
    encontrado = re.search(r"([a-záéíóú]+)\s*(\d{4})?\s*[-–a]+\s*([a-záéíóú]+)\s+(\d{4})", texto, re.I)
    if not encontrado:
        return None
    mes_desde, mes_hasta = mes_de(encontrado.group(1)), mes_de(encontrado.group(3))
    if not mes_desde or not mes_hasta:
        return None
    anio_hasta = int(encontrado.group(4))
    anio_desde = int(encontrado.group(2)) if encontrado.group(2) else anio_hasta - (mes_desde > mes_hasta)
    return date(anio_desde, mes_desde, 1), ultimo_dia_del_mes(anio_hasta, mes_hasta)
