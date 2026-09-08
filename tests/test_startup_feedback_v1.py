from zendoc.db import get_db
from zendoc.startup_analytics import record_finder_search, submit_finder_feedback
from tests.test_milestone1 import make_app


def test_feedback_is_bound_to_own_search_event_and_updatable(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        event_id = record_finder_search(
            {"id": 10},
            category="hospital",
            location="Nadia",
            result_count=2,
            source_tiers={"official_public_directory_not_zendoc_verified": 2},
        )
        get_db().commit()

        first = submit_finder_feedback(
            {"id": 10},
            analytics_event_id=event_id,
            helpful=False,
            reason_code="details_incomplete",
        )
        assert first["helpful"] == 0

        second = submit_finder_feedback(
            {"id": 10},
            analytics_event_id=event_id,
            helpful=True,
        )
        assert second["helpful"] == 1

        rows = get_db().execute(
            "SELECT * FROM product_feedback WHERE analytics_event_id=?",
            (event_id,),
        ).fetchall()
        assert len(rows) == 1

        other_user_blocked = False
        try:
            submit_finder_feedback(
                {"id": 11},
                analytics_event_id=event_id,
                helpful=True,
            )
        except PermissionError:
            other_user_blocked = True
        assert other_user_blocked is True
