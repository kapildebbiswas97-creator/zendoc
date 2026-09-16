import pytest

from zendoc import care_journey_routes


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Db:
    def __init__(self, row):
        self._row = row
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return _Result(self._row)


def test_careloop_boundary_uses_scope_bound_care_graph_authorization(monkeypatch):
    db = _Db({"patient_id": 41})
    calls = []
    monkeypatch.setattr(care_journey_routes, "get_db", lambda: db)
    monkeypatch.setattr(
        care_journey_routes,
        "verify_context_authorization",
        lambda actor, patient_id, purpose: calls.append((actor, patient_id, purpose)),
    )

    actor = {"id": 77, "role": "doctor"}
    care_journey_routes._enforce_careloop_context_scope(actor, action_id=9)

    assert calls == [(actor, 41, "care_graph")]
    assert db.calls[0][1] == (9,)


def test_careloop_boundary_fails_closed_when_action_is_missing(monkeypatch):
    monkeypatch.setattr(care_journey_routes, "get_db", lambda: _Db(None))

    with pytest.raises(LookupError, match="Care action not found"):
        care_journey_routes._enforce_careloop_context_scope({"id": 77}, action_id=999)
