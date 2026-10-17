"""The supported list is stated once and everything that repeats it stays in step."""

from pathlib import Path

from app.domain import envelope
from app.domain.checks import UNSUPPORTED_FEATURES


def test_the_document_is_what_the_code_says():
    doc = Path(__file__).resolve().parents[2] / "docs" / "supported.md"
    assert doc.read_text(encoding="utf-8") == envelope.render_markdown(), "run: python -m app.domain.envelope --write"


def test_every_item_has_a_known_status_and_every_status_is_used():
    assert {c["status"] for c in envelope.CAPABILITIES} == {"yes", "partly", "no"}
    assert len({c["id"] for c in envelope.CAPABILITIES}) == len(envelope.CAPABILITIES)


def test_unsupported_words_are_found_once_each_in_reading_order():
    text = "A house with a basement, a swimming pool, a pool house, a balcony and a curved wall."
    assert envelope.find_unsupported(text) == ["a basement", "a pool", "a balcony", "curved walls"]
    assert envelope.find_unsupported("Two storey house with a kitchen") == []
    assert envelope.find_unsupported("Poolside cabin") == []                      # whole words only


def test_the_checker_treats_the_same_features_as_unbuildable():
    for word in ("basement", "pool", "porch", "balcony", "garden"):
        assert word in UNSUPPORTED_FEATURES and word in envelope.UNSUPPORTED_WORDS


def test_the_api_serves_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import create_app

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    with TestClient(create_app()) as c:
        body = c.get("/api/capabilities").json()
    assert body["capabilities"] == envelope.CAPABILITIES and "basement" in body["unsupported_words"]
