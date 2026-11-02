"""El cliente HTTP respeta lo que pide cada sitio en su robots.txt."""

from urllib.robotparser import RobotFileParser

from cartelera.http import Cliente


def _robots(texto: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(texto.splitlines())
    return parser


def test_la_pausa_es_la_mayor_entre_la_propia_y_el_crawl_delay():
    with Cliente(pausa=1.0) as cliente:
        cliente._robots["https://cabildo.montevideo.gub.uy"] = _robots("User-agent: *\nCrawl-delay: 10\nDisallow: /admin/")
        cliente._robots["https://mnav.gub.uy"] = _robots("User-agent: *\nDisallow:")
        assert cliente._pausa_de("https://cabildo.montevideo.gub.uy/exposiciones") == 10
        assert cliente._pausa_de("https://mnav.gub.uy/cms.php?id=expos") == 1.0
        assert cliente._pausa_de("https://sin-robots.example/") == 1.0
        assert not cliente._permitido("https://cabildo.montevideo.gub.uy/admin/x")
