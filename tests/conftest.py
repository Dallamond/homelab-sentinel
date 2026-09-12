"""
Configuración compartida de pytest.

Garantiza que la DB de test y el backend de resúmenes se fijan ANTES de que
cualquier módulo importe app.*. La raíz del problema: app/db/session.py crea
el engine en tiempo de importación con settings.database_url — si un test
module carga app.db.models antes de setear DATABASE_URL, el engine apunta a
./data/sentinel.db (directorio que no existe en tests) y todo falla.

pytest importa conftest.py antes que cualquier test module, así que esto
cubre test_alert_engine.py y test_stream_grouping.py, que no fijaban la var
por su cuenta.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sentinel.db")
os.environ.setdefault("SUMMARIZER_BACKEND", "none")