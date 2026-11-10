"""Un módulo por fuente. Cada uno expone `NOMBRE` y `scrapear(cliente, ahora)`."""

from cartelera.scrapers import (
    cartelera_mvd, cinemateca, cobraticket, corchea, entraste, fever, galpon, gaucho, gurvich, instagram_bares, ladiaria, mapas_especiales, mapi, mec_museos, mientrada, mnav, museos_im, piano_piano,
    portal_im, propuestos, redtickets, sala_del_museo, salacamacua, sodre, solis, teatro_de_verano, ticketmaster_uy, tikzet, tickantel, torres_garcia, zitarrosa,
)

FUENTES = {
    modulo.NOMBRE: modulo
    for modulo in (
        tickantel, redtickets, sodre, cinemateca, cartelera_mvd, solis, teatro_de_verano, galpon,
        portal_im, zitarrosa, ticketmaster_uy, sala_del_museo, gaucho, piano_piano, ladiaria, fever,
        museos_im, mnav, torres_garcia, gurvich, mapi, mec_museos, salacamacua, mientrada, cobraticket, corchea,
        propuestos, entraste, mapas_especiales, tikzet, instagram_bares,
    )
}
