from pathlib import Path

from pydantic import TypeAdapter

from backend.app.ledger import Ledger
from backend.app.models import Record
from backend.app.routers.records import _ledger_for_path, get_ledger


def test_default_demo_seed_populates_empty_database_and_preserves_edits_on_reopen(tmp_path, monkeypatch):
    path = str(tmp_path / "seeded.db")
    monkeypatch.setenv("DATABASE_URL", path)
    monkeypatch.delenv("SEED_FIXTURES", raising=False)
    fixture_path = Path(__file__).resolve().parents[4] / "contract" / "fixtures" / "records.json"
    expected = TypeAdapter(list[Record]).validate_json(fixture_path.read_text(encoding="utf-8"))

    ledger = get_ledger()
    assert {item.id for item in ledger.list_records()} == {item.id for item in expected}
    for item in expected:
        stored = ledger.get_record(item.id)
        assert stored.model_dump(exclude={"history"}) == item.model_dump(exclude={"history"})
        assert stored.history and stored.history[-1].action == "extracted"
    original = expected[0]
    edited = ledger.update_record(original.id, edits={"amount": 987.0})
    _ledger_for_path.cache_clear()

    reopened = get_ledger()
    assert reopened is not ledger
    assert reopened.get_record(original.id) == edited


def test_seed_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "empty.db"))
    monkeypatch.setenv("SEED_FIXTURES", "0")
    assert get_ledger().list_records() == []


def test_seed_does_not_add_fixtures_to_nonempty_database(tmp_path, monkeypatch):
    from backend.app.routers.tests.test_records_api import make_record

    path = str(tmp_path / "existing.db")
    ledger = Ledger(path)
    ledger.upsert_record(make_record())
    before = ledger.list_events()
    monkeypatch.setenv("DATABASE_URL", path)
    monkeypatch.setenv("SEED_FIXTURES", "1")

    initialized = get_ledger()
    assert [item.id for item in initialized.list_records()] == ["rent-1"]
    assert initialized.list_events() == before
