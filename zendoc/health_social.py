"""Health-only social/community primitives for ZENDOC.

This is a bounded social layer: health education, healthy routines, fitness,
nutrition, caregiving and wellbeing. Community content is user-generated and
must never be represented as verified medical advice merely because it appears
inside ZENDOC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .db import get_db, now_iso

HEALTH_LANES = (
    ("healthy_food", "Healthy food & cooking"),
    ("fitness", "Fitness & movement"),
    ("mental_wellbeing", "Mental wellbeing"),
    ("sleep_recovery", "Sleep & recovery"),
    ("family_care", "Family & caregiving"),
    ("preventive_health", "Preventive health"),
    ("health_devices", "Health devices & IoT"),
    ("care_experience", "Care experience & navigation"),
)
LANE_IDS = {item[0] for item in HEALTH_LANES}


def ensure_health_social_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS health_social_follows (
            follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            followed_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY (follower_id, followed_id)
        );
        CREATE INDEX IF NOT EXISTS idx_health_social_followed
            ON health_social_follows(followed_id, follower_id);

        CREATE TABLE IF NOT EXISTS health_social_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            lane TEXT NOT NULL,
            body TEXT NOT NULL,
            media_type TEXT NOT NULL DEFAULT 'text',
            media_url TEXT,
            media_storage_key TEXT,
            media_mime_type TEXT,
            media_original_name TEXT,
            media_size_bytes INTEGER,
            sponsorship_label TEXT,
            visibility TEXT NOT NULL DEFAULT 'community',
            moderation_status TEXT NOT NULL DEFAULT 'published',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_social_posts_feed
            ON health_social_posts(moderation_status, created_at, id);
        CREATE INDEX IF NOT EXISTS idx_health_social_posts_author
            ON health_social_posts(author_id, created_at, id);

        CREATE TABLE IF NOT EXISTS health_social_stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            lane TEXT NOT NULL,
            body TEXT NOT NULL,
            media_url TEXT,
            media_storage_key TEXT,
            media_mime_type TEXT,
            media_original_name TEXT,
            media_size_bytes INTEGER,
            moderation_status TEXT NOT NULL DEFAULT 'published',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_social_stories_active
            ON health_social_stories(expires_at, moderation_status);

        CREATE TABLE IF NOT EXISTS health_social_likes (
            post_id INTEGER NOT NULL REFERENCES health_social_posts(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS health_social_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES health_social_posts(id) ON DELETE CASCADE,
            author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            moderation_status TEXT NOT NULL DEFAULT 'published',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_social_comments_post
            ON health_social_comments(post_id, created_at, id);

        CREATE TABLE IF NOT EXISTS health_social_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_social_reports_status
            ON health_social_reports(status, entity_type, entity_id);

        CREATE TABLE IF NOT EXISTS health_social_blocks (
            blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY (blocker_id, blocked_id)
        );
        """
    )


def lane_catalog():
    return [{"id": lane_id, "label": label} for lane_id, label in HEALTH_LANES]


def _user_id(user) -> int:
    return int(user["id"])


def _clean_lane(value) -> str:
    lane = str(value or "").strip().lower()
    if lane not in LANE_IDS:
        raise ValueError("Choose a supported health content lane.")
    return lane


def _clean_body(value, limit=2000) -> str:
    body = " ".join(str(value or "").strip().split())
    if not body:
        raise ValueError("Write something before publishing.")
    if len(body) > limit:
        raise ValueError(f"Content must be {limit} characters or fewer.")
    return body


def _clean_media_url(value) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Media links must use a valid HTTPS URL.")
    return url[:1000]


def _blocked_pair_clause():
    return """
        NOT EXISTS (
            SELECT 1 FROM health_social_blocks b
            WHERE (b.blocker_id=? AND b.blocked_id=u.id)
               OR (b.blocker_id=u.id AND b.blocked_id=?)
        )
    """


def create_post(user, data) -> dict:
    ensure_health_social_schema()
    body = _clean_body(data.get("body"))
    lane = _clean_lane(data.get("lane"))
    media_url = _clean_media_url(data.get("media_url"))
    media_storage_key = str(data.get("media_storage_key") or "").strip() or None
    media_mime_type = str(data.get("media_mime_type") or "").strip() or None
    media_original_name = str(data.get("media_original_name") or "").strip()[:255] or None
    media_size_bytes = int(data.get("media_size_bytes") or 0) or None
    media_kind = str(data.get("media_kind") or "").strip().lower()
    if media_storage_key and media_url:
        raise ValueError("Choose either an uploaded media file or an external media link, not both.")
    if media_storage_key:
        if media_kind not in {"image", "video"} or not media_mime_type:
            raise ValueError("Uploaded community media metadata is invalid.")
        media_type = media_kind
    else:
        media_type = "external_link" if media_url else "text"
    sponsorship = str(data.get("sponsorship_label") or "").strip()[:160] or None
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO health_social_posts
        (author_id,lane,body,media_type,media_url,media_storage_key,media_mime_type,
         media_original_name,media_size_bytes,sponsorship_label,visibility,moderation_status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,'community','published',?,?)
        """,
        (
            _user_id(user), lane, body, media_type, media_url, media_storage_key,
            media_mime_type, media_original_name, media_size_bytes, sponsorship, now, now,
        ),
    )
    get_db().commit()
    return get_post(user, int(cursor.lastrowid))


def get_post(user, post_id: int) -> dict:
    ensure_health_social_schema()
    uid = _user_id(user)
    row = get_db().execute(
        f"""
        SELECT p.*,u.name author_name,u.role author_role,
               (SELECT COUNT(*) FROM health_social_likes l WHERE l.post_id=p.id) like_count,
               (SELECT COUNT(*) FROM health_social_comments c WHERE c.post_id=p.id AND c.moderation_status='published') comment_count,
               EXISTS(SELECT 1 FROM health_social_likes l WHERE l.post_id=p.id AND l.user_id=?) liked_by_me
        FROM health_social_posts p
        JOIN users u ON u.id=p.author_id
        WHERE p.id=? AND p.moderation_status='published' AND {_blocked_pair_clause()}
        """,
        (uid, int(post_id), uid, uid),
    ).fetchone()
    if not row:
        raise LookupError("Community post not found.")
    item = dict(row)
    item["community_notice"] = "User-generated content; not verified medical advice."
    return item


def list_feed(user, *, followed_only=False, limit=50) -> list[dict]:
    ensure_health_social_schema()
    uid = _user_id(user)
    limit = max(1, min(int(limit or 50), 100))
    followed_sql = "AND (p.author_id=? OR EXISTS(SELECT 1 FROM health_social_follows f WHERE f.follower_id=? AND f.followed_id=p.author_id))" if followed_only else ""
    params = [uid, uid, uid, uid]
    if followed_only:
        params.extend([uid, uid])
    params.append(limit)
    rows = get_db().execute(
        f"""
        SELECT p.*,u.name author_name,u.role author_role,
               (SELECT COUNT(*) FROM health_social_likes l WHERE l.post_id=p.id) like_count,
               (SELECT COUNT(*) FROM health_social_comments c WHERE c.post_id=p.id AND c.moderation_status='published') comment_count,
               EXISTS(SELECT 1 FROM health_social_likes l WHERE l.post_id=p.id AND l.user_id=?) liked_by_me,
               EXISTS(SELECT 1 FROM health_social_follows f WHERE f.follower_id=? AND f.followed_id=p.author_id) followed_by_me
        FROM health_social_posts p
        JOIN users u ON u.id=p.author_id
        WHERE p.moderation_status='published'
          AND {_blocked_pair_clause()}
          {followed_sql}
        ORDER BY p.created_at DESC,p.id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def create_story(user, data) -> dict:
    ensure_health_social_schema()
    lane = _clean_lane(data.get("lane"))
    body = _clean_body(data.get("body"), 700)
    media_url = _clean_media_url(data.get("media_url"))
    media_storage_key = str(data.get("media_storage_key") or "").strip() or None
    media_mime_type = str(data.get("media_mime_type") or "").strip() or None
    media_original_name = str(data.get("media_original_name") or "").strip()[:255] or None
    media_size_bytes = int(data.get("media_size_bytes") or 0) or None
    media_kind = str(data.get("media_kind") or "").strip().lower()
    if media_storage_key and media_url:
        raise ValueError("Choose either an uploaded media file or an external media link, not both.")
    if media_storage_key and (media_kind not in {"image", "video"} or not media_mime_type):
        raise ValueError("Uploaded community media metadata is invalid.")
    now = now_iso()
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")
    cursor = get_db().execute(
        """
        INSERT INTO health_social_stories
        (author_id,lane,body,media_url,media_storage_key,media_mime_type,media_original_name,
         media_size_bytes,moderation_status,created_at,expires_at)
        VALUES (?,?,?,?,?,?,?,?,'published',?,?)
        """,
        (
            _user_id(user), lane, body, media_url, media_storage_key, media_mime_type,
            media_original_name, media_size_bytes, now, expires,
        ),
    )
    get_db().commit()
    return {"id": int(cursor.lastrowid), "expires_at": expires}


def list_stories(user, *, limit=40) -> list[dict]:
    ensure_health_social_schema()
    uid = _user_id(user)
    rows = get_db().execute(
        f"""
        SELECT s.*,u.name author_name,u.role author_role
        FROM health_social_stories s
        JOIN users u ON u.id=s.author_id
        WHERE s.moderation_status='published' AND s.expires_at>?
          AND {_blocked_pair_clause()}
        ORDER BY s.created_at DESC,s.id DESC
        LIMIT ?
        """,
        (now_iso(), uid, uid, max(1, min(int(limit or 40), 80))),
    ).fetchall()
    return [dict(row) for row in rows]


def follow_user(user, target_user_id: int) -> None:
    ensure_health_social_schema()
    uid, target = _user_id(user), int(target_user_id)
    if uid == target:
        raise ValueError("You cannot follow yourself.")
    row = get_db().execute("SELECT id FROM users WHERE id=? AND active=1", (target,)).fetchone()
    if not row:
        raise LookupError("User not found.")
    blocked = get_db().execute(
        "SELECT 1 FROM health_social_blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)",
        (uid, target, target, uid),
    ).fetchone()
    if blocked:
        raise PermissionError("Following is unavailable because one account has blocked the other.")
    exists = get_db().execute(
        "SELECT 1 FROM health_social_follows WHERE follower_id=? AND followed_id=?",
        (uid, target),
    ).fetchone()
    if not exists:
        get_db().execute(
            "INSERT INTO health_social_follows (follower_id,followed_id,created_at) VALUES (?,?,?)",
            (uid, target, now_iso()),
        )
        get_db().commit()


def unfollow_user(user, target_user_id: int) -> None:
    ensure_health_social_schema()
    get_db().execute(
        "DELETE FROM health_social_follows WHERE follower_id=? AND followed_id=?",
        (_user_id(user), int(target_user_id)),
    )
    get_db().commit()


def toggle_like(user, post_id: int) -> bool:
    ensure_health_social_schema()
    get_post(user, post_id)
    uid = _user_id(user)
    existing = get_db().execute(
        "SELECT 1 FROM health_social_likes WHERE post_id=? AND user_id=?",
        (int(post_id), uid),
    ).fetchone()
    if existing:
        get_db().execute("DELETE FROM health_social_likes WHERE post_id=? AND user_id=?", (int(post_id), uid))
        liked = False
    else:
        get_db().execute(
            "INSERT INTO health_social_likes (post_id,user_id,created_at) VALUES (?,?,?)",
            (int(post_id), uid, now_iso()),
        )
        liked = True
    get_db().commit()
    return liked


def add_comment(user, post_id: int, body) -> dict:
    ensure_health_social_schema()
    get_post(user, post_id)
    clean = _clean_body(body, 700)
    cursor = get_db().execute(
        """
        INSERT INTO health_social_comments (post_id,author_id,body,moderation_status,created_at)
        VALUES (?,?,?,'published',?)
        """,
        (int(post_id), _user_id(user), clean, now_iso()),
    )
    get_db().commit()
    return {"id": int(cursor.lastrowid), "body": clean}


def list_comments(user, post_id: int, *, limit=5) -> list[dict]:
    ensure_health_social_schema()
    get_post(user, post_id)
    rows = get_db().execute(
        """
        SELECT c.*,u.name author_name,u.role author_role
        FROM health_social_comments c JOIN users u ON u.id=c.author_id
        WHERE c.post_id=? AND c.moderation_status='published'
        ORDER BY c.created_at DESC,c.id DESC LIMIT ?
        """,
        (int(post_id), max(1, min(int(limit or 5), 30))),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def report_entity(user, entity_type: str, entity_id: int, reason) -> int:
    ensure_health_social_schema()
    kind = str(entity_type or "").strip().lower()
    if kind not in {"post", "story", "comment", "user"}:
        raise ValueError("Unsupported report type.")
    why = _clean_body(reason, 500)
    cursor = get_db().execute(
        """
        INSERT INTO health_social_reports (reporter_id,entity_type,entity_id,reason,status,created_at)
        VALUES (?,?,?,?, 'open', ?)
        """,
        (_user_id(user), kind, int(entity_id), why, now_iso()),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def block_user(user, target_user_id: int) -> None:
    ensure_health_social_schema()
    uid, target = _user_id(user), int(target_user_id)
    if uid == target:
        raise ValueError("You cannot block yourself.")
    exists = get_db().execute(
        "SELECT 1 FROM health_social_blocks WHERE blocker_id=? AND blocked_id=?",
        (uid, target),
    ).fetchone()
    if not exists:
        get_db().execute(
            "INSERT INTO health_social_blocks (blocker_id,blocked_id,created_at) VALUES (?,?,?)",
            (uid, target, now_iso()),
        )
    get_db().execute(
        "DELETE FROM health_social_follows WHERE (follower_id=? AND followed_id=?) OR (follower_id=? AND followed_id=?)",
        (uid, target, target, uid),
    )
    get_db().commit()


def discover_people(user, query="", *, limit=20) -> list[dict]:
    ensure_health_social_schema()
    uid = _user_id(user)
    q = " ".join(str(query or "").strip().split())[:120]
    like = f"%{q.lower()}%"
    rows = get_db().execute(
        f"""
        SELECT u.id,u.name,u.role,
               EXISTS(SELECT 1 FROM health_social_follows f WHERE f.follower_id=? AND f.followed_id=u.id) followed_by_me
        FROM users u
        WHERE u.active=1 AND u.id<>?
          AND {_blocked_pair_clause()}
          AND (?='' OR LOWER(u.name) LIKE ? OR LOWER(u.role) LIKE ?)
        ORDER BY followed_by_me DESC,u.name
        LIMIT ?
        """,
        (uid, uid, uid, uid, q, like, like, max(1, min(int(limit or 20), 50))),
    ).fetchall()
    return [dict(row) for row in rows]


def list_moderation_reports(*, status="open", limit=100) -> list[dict]:
    """Owner-facing moderation queue. Authorization belongs at the route layer."""
    ensure_health_social_schema()
    wanted = str(status or "open").strip().lower()
    rows = get_db().execute(
        """
        SELECT r.*,u.name reporter_name,u.email reporter_email
        FROM health_social_reports r
        JOIN users u ON u.id=r.reporter_id
        WHERE (?='all' OR r.status=?)
        ORDER BY r.created_at ASC,r.id ASC
        LIMIT ?
        """,
        (wanted, wanted, max(1, min(int(limit or 100), 250))),
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        entity_type = item["entity_type"]
        entity_id = int(item["entity_id"])
        preview = None
        author_name = None
        if entity_type == "post":
            target = get_db().execute(
                """
                SELECT p.body,p.moderation_status,u.name author_name
                FROM health_social_posts p JOIN users u ON u.id=p.author_id
                WHERE p.id=?
                """,
                (entity_id,),
            ).fetchone()
        elif entity_type == "story":
            target = get_db().execute(
                """
                SELECT s.body,s.moderation_status,u.name author_name
                FROM health_social_stories s JOIN users u ON u.id=s.author_id
                WHERE s.id=?
                """,
                (entity_id,),
            ).fetchone()
        elif entity_type == "comment":
            target = get_db().execute(
                """
                SELECT c.body,c.moderation_status,u.name author_name
                FROM health_social_comments c JOIN users u ON u.id=c.author_id
                WHERE c.id=?
                """,
                (entity_id,),
            ).fetchone()
        elif entity_type == "user":
            target = get_db().execute(
                "SELECT name author_name,'Account report' body,'active' moderation_status FROM users WHERE id=?",
                (entity_id,),
            ).fetchone()
        else:
            target = None
        if target:
            preview = str(target["body"] or "")[:500]
            author_name = target["author_name"]
            item["target_status"] = target["moderation_status"]
        else:
            item["target_status"] = "missing"
        item["target_preview"] = preview
        item["target_author_name"] = author_name
        results.append(item)
    return results


def moderate_report(report_id: int, action: str) -> dict:
    """Resolve one report without silently disabling user accounts."""
    ensure_health_social_schema()
    row = get_db().execute(
        "SELECT * FROM health_social_reports WHERE id=?",
        (int(report_id),),
    ).fetchone()
    if not row:
        raise LookupError("Community report not found.")
    if str(row["status"]) != "open":
        raise ValueError("This community report has already been resolved.")

    action = str(action or "").strip().lower()
    if action not in {"remove", "dismiss"}:
        raise ValueError("Moderation action must be remove or dismiss.")

    entity_type = str(row["entity_type"])
    entity_id = int(row["entity_id"])
    if action == "remove":
        table_by_type = {
            "post": "health_social_posts",
            "story": "health_social_stories",
            "comment": "health_social_comments",
        }
        table = table_by_type.get(entity_type)
        if not table:
            raise ValueError(
                "Account reports require manual owner investigation; they are not auto-disabled from the community queue."
            )
        target = get_db().execute(f"SELECT id FROM {table} WHERE id=?", (entity_id,)).fetchone()
        if target:
            get_db().execute(
                f"UPDATE {table} SET moderation_status='removed' WHERE id=?",
                (entity_id,),
            )
        resolution = "resolved_removed"
    else:
        resolution = "dismissed"

    get_db().execute(
        "UPDATE health_social_reports SET status=? WHERE id=?",
        (resolution, int(report_id)),
    )
    get_db().commit()
    return {
        "report_id": int(report_id),
        "status": resolution,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }


def get_community_media_access(user, storage_key: str) -> dict:
    """Resolve media only when the signed-in viewer can see its live content."""
    ensure_health_social_schema()
    uid = _user_id(user)
    key = str(storage_key or "").strip()
    if not key:
        raise LookupError("Community media not found.")

    post = get_db().execute(
        f"""
        SELECT p.media_storage_key,p.media_mime_type,p.media_original_name,p.media_size_bytes,
               p.author_id,u.name author_name,'post' entity_type
        FROM health_social_posts p
        JOIN users u ON u.id=p.author_id
        WHERE p.media_storage_key=? AND p.moderation_status='published'
          AND {_blocked_pair_clause()}
        LIMIT 1
        """,
        (key, uid, uid),
    ).fetchone()
    if post:
        return dict(post)

    story = get_db().execute(
        f"""
        SELECT s.media_storage_key,s.media_mime_type,s.media_original_name,s.media_size_bytes,
               s.author_id,u.name author_name,'story' entity_type
        FROM health_social_stories s
        JOIN users u ON u.id=s.author_id
        WHERE s.media_storage_key=? AND s.moderation_status='published' AND s.expires_at>?
          AND {_blocked_pair_clause()}
        LIMIT 1
        """,
        (key, now_iso(), uid, uid),
    ).fetchone()
    if story:
        return dict(story)
    raise LookupError("Community media is unavailable.")


def unblock_user(user, target_user_id: int) -> None:
    ensure_health_social_schema()
    get_db().execute(
        "DELETE FROM health_social_blocks WHERE blocker_id=? AND blocked_id=?",
        (_user_id(user), int(target_user_id)),
    )
    get_db().commit()


def blocked_user_ids(user) -> set[int]:
    ensure_health_social_schema()
    rows = get_db().execute(
        "SELECT blocked_id FROM health_social_blocks WHERE blocker_id=? ORDER BY created_at DESC",
        (_user_id(user),),
    ).fetchall()
    return {int(row["blocked_id"]) for row in rows}


def list_blocked_users(user, *, limit=100) -> list[dict]:
    ensure_health_social_schema()
    rows = get_db().execute(
        """
        SELECT u.id,u.name,u.role,b.created_at
        FROM health_social_blocks b
        JOIN users u ON u.id=b.blocked_id
        WHERE b.blocker_id=?
        ORDER BY b.created_at DESC,u.name
        LIMIT ?
        """,
        (_user_id(user), max(1, min(int(limit or 100), 250))),
    ).fetchall()
    return [dict(row) for row in rows]
