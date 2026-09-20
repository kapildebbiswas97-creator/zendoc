from zendoc.db import get_db
from tests.test_milestone1 import csrf, login_web, make_app, register_web


def test_mental_wellness_private_history_and_journal(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "wellness-owner@example.com", "Wellness Owner")
    login_web(client, "patient", "wellness-owner@example.com")

    page = client.get("/mental-wellness")
    assert page.status_code == 200
    token = csrf(page.data.decode())
    saved = client.post(
        "/mental-wellness",
        data={
            "csrf_token": token,
            "action": "checkin",
            "mood_level": "7",
            "stress_level": "4",
            "energy_level": "6",
            "sleep_quality": "8",
            "note": "A calmer day.",
        },
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert b"Private wellbeing check-in saved." in saved.data
    assert b"Mood 7/10" in saved.data

    token = csrf(saved.data.decode())
    journal = client.post(
        "/mental-wellness",
        data={
            "csrf_token": token,
            "action": "journal",
            "title": "Private reflection",
            "body": "This belongs only to my account.",
        },
        follow_redirects=True,
    )
    assert journal.status_code == 200
    assert b"Private journal entry saved." in journal.data
    assert b"This belongs only to my account." in journal.data

    with app.app_context():
        row = get_db().execute(
            "SELECT id,user_id FROM mental_wellness_journal WHERE title=?",
            ("Private reflection",),
        ).fetchone()
        assert row is not None
        entry_id = int(row["id"])

    other = app.test_client()
    register_web(other, "patient", "wellness-other@example.com", "Wellness Other")
    login_web(other, "patient", "wellness-other@example.com")
    other_page = other.get("/mental-wellness")
    assert b"This belongs only to my account." not in other_page.data

    other_token = csrf(other_page.data.decode())
    denied = other.post(
        "/mental-wellness",
        data={"csrf_token": other_token, "action": "delete_journal", "entry_id": entry_id},
        follow_redirects=True,
    )
    assert b"Private journal entry not found." in denied.data

    owner_page = client.get("/mental-wellness")
    owner_token = csrf(owner_page.data.decode())
    deleted = client.post(
        "/mental-wellness",
        data={"csrf_token": owner_token, "action": "delete_journal", "entry_id": entry_id},
        follow_redirects=True,
    )
    assert b"Private journal entry deleted." in deleted.data


def test_community_save_share_and_author_delete(tmp_path):
    app = make_app(tmp_path)
    author = app.test_client()
    viewer = app.test_client()
    register_web(author, "patient", "social-author@example.com", "Social Author")
    register_web(viewer, "patient", "social-viewer@example.com", "Social Viewer")
    login_web(author, "patient", "social-author@example.com")
    login_web(viewer, "patient", "social-viewer@example.com")

    page = author.get("/community")
    token = csrf(page.data.decode())
    created = author.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "post",
            "lane": "fitness",
            "body": "A real community post for save and share testing.",
            "accept_guidelines": "1",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    with app.app_context():
        post_id = int(get_db().execute(
            "SELECT id FROM health_social_posts WHERE body=?",
            ("A real community post for save and share testing.",),
        ).fetchone()["id"])

    viewer_page = viewer.get("/community")
    viewer_token = csrf(viewer_page.data.decode())
    saved = viewer.post(
        "/community",
        data={"csrf_token": viewer_token, "action": "save", "post_id": post_id},
        follow_redirects=True,
    )
    assert b"Post saved." in saved.data
    saved_feed = viewer.get("/community?mode=saved")
    assert b"A real community post for save and share testing." in saved_feed.data

    detail = viewer.get(f"/community/posts/{post_id}")
    assert detail.status_code == 200
    assert b"A stable page you can share" in detail.data

    viewer_token = csrf(saved.data.decode())
    forbidden = viewer.post(
        "/community",
        data={"csrf_token": viewer_token, "action": "delete_post", "post_id": post_id},
        follow_redirects=True,
    )
    assert b"You can only delete your own community posts." in forbidden.data

    author_page = author.get("/community")
    author_token = csrf(author_page.data.decode())
    removed = author.post(
        "/community",
        data={"csrf_token": author_token, "action": "delete_post", "post_id": post_id},
        follow_redirects=True,
    )
    assert b"Your community post was deleted." in removed.data
    assert viewer.get(f"/community/posts/{post_id}").status_code == 404
