"""Web and mobile API routes for the ZENDOC health-only community."""
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .health_social import (
    add_comment,
    block_user,
    create_post,
    create_story,
    discover_people,
    follow_user,
    lane_catalog,
    list_comments,
    list_feed,
    list_stories,
    list_moderation_reports,
    moderate_report,
    report_entity,
    toggle_like,
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
        add_comment(user, int(data.get("post_id")), data.get("body"))
        return "Comment added."
    if action == "report":
        report_entity(user, data.get("entity_type"), int(data.get("entity_id")), data.get("reason"))
        return "Report sent for review."
    if action == "block":
        block_user(user, int(data.get("target_user_id")))
        return "Account blocked. Their community content is now hidden."
    raise ValueError("Unsupported community action.")


@bp.route("/community", methods=("GET", "POST"))
@login_required
def community_page():
    if request.method == "POST":
        try:
            flash(_handle_action(g.user, request.form), "success")
        except (ValueError, LookupError, PermissionError) as error:
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
