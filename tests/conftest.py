from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MONTEVIDEO = ZoneInfo("America/Montevideo")


@pytest.fixture
def pagina():
    def leer(nombre: str) -> str:
        return (FIXTURES / nombre).read_text(encoding="utf-8")
    return leer


@pytest.fixture
def ahora():
    """El momento en que se guardaron las páginas de ejemplo."""
    return datetime(2026, 10, 30, 12, 0, tzinfo=MONTEVIDEO)
