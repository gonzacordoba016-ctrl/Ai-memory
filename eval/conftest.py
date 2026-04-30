import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """CircuitDesignManager usando DB temporal (no contamina la real)."""
    db_file = str(tmp_path / "test_circuits.db")
    monkeypatch.setenv("MEMORY_DB_PATH", db_file)
    import database.circuit_design as cd_mod
    original = cd_mod.DB_PATH
    cd_mod.DB_PATH = db_file
    yield db_file
    cd_mod.DB_PATH = original
