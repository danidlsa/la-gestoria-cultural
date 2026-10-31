"""Un módulo por fuente. Cada uno expone `NOMBRE` y `scrapear(cliente, ahora)`."""

from cartelera.scrapers import (
    cartelera_mvd, cinemateca, fever, galpon, gaucho, ladiaria, piano_piano, portal_im, redtickets, sala_del_museo, sodre,
    solis, teatro_de_verano, ticketmaster_uy, tickantel, zitarrosa,
)

FUENTES = {
    modulo.NOMBRE: modulo
    for modulo in (
        tickantel, redtickets, sodre, cinemateca, cartelera_mvd, solis, teatro_de_verano, galpon,
        portal_im, zitarrosa, ticketmaster_uy, sala_del_museo, gaucho, piano_piano, ladiaria, fever,
    )
}
