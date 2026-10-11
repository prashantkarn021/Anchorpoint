from datetime import UTC, date, datetime
from types import SimpleNamespace as NS

import plaid
import pytest

from backend.app.connectors import plaid as plaid_conn
from backend.app.connectors.plaid import PlaidConnector, to_raw_item


def _t(tid, amount=1150.0, merchant=None, pending=False, d=date(2026, 9, 2)):
    return NS(transaction_id=tid, date=d, name="WESTPORT PROPERTY MGMT ACH", merchant_name=merchant,
              amount=amount, pending=pending, account_id="acc1", iso_currency_code="USD")


def _page(added=(), modified=(), removed=(), more=False, status="HISTORICAL_UPDATE_COMPLETE", cur="c"):
    return NS(added=list(added), modified=list(modified), removed=list(removed), has_more=more,
              next_cursor=cur, transactions_update_status=status)


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0

    def transactions_sync(self, req):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _conn(responses, monkeypatch) -> PlaidConnector:
    monkeypatch.setattr(plaid_conn.time, "sleep", lambda s: None)
    c = PlaidConnector([], client=FakeClient(responses))
    c._access_token = "test-token"
    return c


def test_to_raw_item_maps_fields_and_keeps_sign():
    r = to_raw_item(_t("t1"))
    assert (r.provider, r.source_id) == ("bank", "t1")
    assert r.received_at == datetime(2026, 9, 2, tzinfo=UTC)
    assert r.meta["merchant"] == "WESTPORT PROPERTY MGMT ACH" and r.meta["merchant_name"] is None
    assert r.meta["amount"] == 1150.0 and "(debit)" in r.text
    credit = to_raw_item(_t("t2", amount=-920.0, merchant="Westport Prop"))  # Plaid's guess stays a hint
    assert credit.meta["merchant"] == "WESTPORT PROPERTY MGMT ACH" and credit.meta["merchant_name"] == "Westport Prop"
    assert credit.meta["amount"] == -920.0
    assert "(credit)" in credit.text


def test_paginates_skips_pending_and_keeps_modified(monkeypatch):
    c = _conn([_page(added=[_t("a"), _t("p", pending=True)], more=True, cur="c1"),
               _page(modified=[_t("m")], removed=[NS(transaction_id="x")], cur="c2")], monkeypatch)
    items, cursor = c.fetch_since("c0")
    assert [i.source_id for i in items] == ["a", "m"] and cursor == "c2"


def test_restarts_on_mutation_during_pagination(monkeypatch):
    err = plaid.ApiException(status=400)
    err.body = '{"error_code": "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"}'
    c = _conn([_page(added=[_t("a")], more=True), err, _page(added=[_t("a")], more=True), _page(added=[_t("b")])],
              monkeypatch)
    items, _ = c.fetch_since("c0")
    assert [i.source_id for i in items] == ["a", "b"]  # no duplicate "a" from the aborted pass


def test_mutation_retries_stop_at_deadline(monkeypatch):
    err = plaid.ApiException(status=400)
    err.body = '{"error_code": "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"}'
    c = _conn([err, err], monkeypatch)
    monkeypatch.setattr(plaid_conn, "HISTORY_WAIT_S", 0)
    with pytest.raises(plaid.ApiException):
        c.fetch_since("c0")
    assert c.client.calls == 1


def test_other_api_errors_raise(monkeypatch):
    err = plaid.ApiException(status=400)
    err.body = '{"error_code": "ITEM_LOGIN_REQUIRED"}'
    with pytest.raises(plaid.ApiException):
        _conn([err], monkeypatch).fetch_since("c0")


def test_first_sync_waits_for_history_and_a_stable_count(monkeypatch):
    # seen live: HISTORICAL_UPDATE_COMPLETE arrives while only part of the history is readable
    c = _conn([_page(status="NOT_READY"),
               _page(added=[_t("a")]),             # "complete" but partial
               _page(added=[_t("a"), _t("b")]),    # count still moving
               _page(added=[_t("a"), _t("b")])],   # same count twice -> settled
              monkeypatch)
    items, _ = c.fetch_since(None)
    assert [i.source_id for i in items] == ["a", "b"] and c.client.calls == 4


def test_later_syncs_dont_wait(monkeypatch):
    c = _conn([_page(added=[_t("a")], status="INITIAL_UPDATE_COMPLETE")], monkeypatch)
    assert len(c.fetch_since("c0")[0]) == 1 and c.client.calls == 1


def test_fetch_requires_connection(monkeypatch):
    c = _conn([], monkeypatch)
    c._access_token = None
    with pytest.raises(RuntimeError):
        c.fetch_since(None)
