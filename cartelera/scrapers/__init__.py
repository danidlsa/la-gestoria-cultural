"""Un módulo por fuente. Cada uno expone `NOMBRE` y `scrapear(cliente, ahora)`."""

from cartelera.scrapers import (
    cartelera_mvd, cinemateca, galpon, portal_im, redtickets, sodre, solis, teatro_de_verano, ticketmaster_uy, tickantel,
    zitarrosa,
)

FUENTES = {
    modulo.NOMBRE: modulo
    for modulo in (
        tickantel, redtickets, sodre, cinemateca, cartelera_mvd, solis, teatro_de_verano, galpon,
        portal_im, zitarrosa, ticketmaster_uy,
    )
}
