"""Web and mobile API routes for the ZENDOC health-only community."""
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .community_media import get_community_media_storage
from .health_social import (
    add_comment,
    block_user,
    create_post,
    create_story,
    discover_people,
    follow_user,
    get_community_media_access,
    lane_catalog,
    list_blocked_users,
    list_comments,
    list_feed,
    list_stories,
    list_moderation_reports,
    moderate_report,
    report_entity,
    toggle_like,
    unblock_user,
    unfollow_user,
)
from .policy_acceptance import COMMUNITY_GUIDELINES_VERSION, record_policy_acceptance
from .routes import audit, require_api_user
from .security import login_required, owner_required

bp = Blueprint("health_social", __name__)


def _require_guidelines_acceptance(user, data):
    accepted = data.get("accept_guidelines")
    if accepted not in (True, 1, "1", "true", "on", "yes"):
        raise PermissionError("Accept the current Health Community Guidelines before publishing.")
    record_policy_acceptance(
        int(user["id"]),
        "community_guidelines",
        COMMUNITY_GUIDELINES_VERSION,
        source="community_publish",
    )


def _publish_payload_with_media(data, upload):
    payload = dict(data)
    stored = None
    if upload and getattr(upload, "filename", ""):
        if str(payload.get("media_url") or "").strip():
            raise ValueError("Choose either a native upload or an external media link, not both.")
        stored = get_community_media_storage().save(upload)
        payload.update({
            "media_storage_key": stored.storage_key,
            "media_mime_type": stored.mime_type,
            "media_original_name": stored.original_filename,
            "media_size_bytes": stored.size_bytes,
            "media_kind": stored.media_kind,
        })
    return payload, stored


def _handle_action(user, data):
    action = str(data.get("action") or "").strip()
    if action == "post":
        _require_guidelines_acceptance(user, data)
        item = create_post(user, data)
        audit("create", "health_social_post", str(item["id"]), actor=user)
        return "Health community post published."
    if action == "story":
        _require_guidelines_acceptance(user, data)
        item = create_story(user, data)
        audit("create", "health_social_story", str(item["id"]), actor=user)
        return "Health story published for 24 hours."
    if action == "follow":
        follow_user(user, int(data.get("target_user_id")))
        return "Following updated."
    if action == "unfollow":
        unfollow_user(user, int(data.get("target_user_id")))
        return "Following updated."
    if action == "like":
        liked = toggle_like(user, int(data.get("post_id")))
        return "Post liked." if liked else "Like removed."
    if action == "comment":
        _require_guidelines_acceptance(user, data)
        add_comment(user, int(data.get("post_id")), data.get("body"))
        return "Comment added."
    if action == "report":
        report_entity(user, data.get("entity_type"), int(data.get("entity_id")), data.get("reason"))
        return "Report sent for review."
    if action == "block":
        block_user(user, int(data.get("target_user_id")))
        return "Account blocked. Their community content is now hidden and private communication is unavailable."
    if action == "unblock":
        unblock_user(user, int(data.get("target_user_id")))
        return "Account unblocked. Normal community and communication rules apply again."
    raise ValueError("Unsupported community action.")


@bp.route("/community", methods=("GET", "POST"))
@login_required
def community_page():
    if request.method == "POST":
        stored = None
        try:
            action = str(request.form.get("action") or "").strip()
            payload = request.form
            if action in {"post", "story"}:
                payload, stored = _publish_payload_with_media(
                    request.form.to_dict(),
                    request.files.get("media_file"),
                )
            flash(_handle_action(g.user, payload), "success")
            stored = None
        except (ValueError, LookupError, PermissionError, RuntimeError) as error:
            if stored is not None:
                try:
                    get_community_media_storage().delete(stored.storage_key)
                except Exception:
                    pass
            flash(str(error), "error")
        return redirect(url_for("health_social.community_page", mode=request.args.get("mode", "all")))

    mode = request.args.get("mode", "all")
    feed = list_feed(g.user, followed_only=(mode == "following"))
    for post in feed:
        post["comments"] = list_comments(g.user, int(post["id"]), limit=3)
    return render_template(
        "community.html",
        lanes=lane_catalog(),
        feed=feed,
        stories=list_stories(g.user),
        people=discover_people(g.user, request.args.get("q", "")),
        q=request.args.get("q", ""),
        mode=mode,
        media_storage=get_community_media_storage().status(),
        blocked_users=list_blocked_users(g.user),
    )


@bp.get("/api/v1/community/feed")
def api_feed():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"posts": list_feed(user, followed_only=request.args.get("mode") == "following")})


@bp.post("/api/v1/community/posts")
def api_create_post():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        _require_guidelines_acceptance(user, data)
        post = create_post(user, data)
        audit("create", "health_social_post", str(post["id"]), actor=user)
        return jsonify({"post": post}), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/community/stories")
def api_create_story():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        _require_guidelines_acceptance(user, data)
        story = create_story(user, data)
        audit("create", "health_social_story", str(story["id"]), actor=user)
        return jsonify({"story": story}), 201
    except (ValueError, LookupError, PermissionError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.post("/api/v1/community/action")
def api_action():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        message = _handle_action(user, data)
        return jsonify({"status": "ok", "message": message})
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except LookupError as exc:
        return jsonify({"error": {"code": 404, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.route("/admin/community-moderation", methods=("GET", "POST"))
@login_required
@owner_required
def community_moderation_page():
    if request.method == "POST":
        try:
            result = moderate_report(
                int(request.form.get("report_id")),
                request.form.get("moderation_action"),
            )
            audit(
                "moderate",
                "health_social_report",
                str(result["report_id"]),
                actor=g.user,
            )
            flash(
                "Community report resolved. Removed content is no longer visible in community feeds."
                if result["status"] == "resolved_removed"
                else "Community report dismissed after owner review.",
                "success",
            )
        except (TypeError, ValueError, LookupError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("health_social.community_moderation_page"))

    return render_template(
        "community_moderation.html",
        reports=list_moderation_reports(status=request.args.get("status", "open")),
        selected_status=request.args.get("status", "open"),
    )


@bp.get("/community/media/<path:storage_key>")
@login_required
def community_media_file(storage_key):
    try:
        media = get_community_media_access(g.user, storage_key)
        return get_community_media_storage().response(
            media["media_storage_key"],
            mime_type=media["media_mime_type"],
            download_name=media["media_original_name"] or "zendoc-community-media",
        )
    except (LookupError, ValueError, RuntimeError):
        return ("Community media unavailable.", 404)
