"""Identity verification UI plus signed external eKYC callback boundary."""
from flask import Blueprint,flash,g,jsonify,redirect,render_template,request,url_for

from .identity_verification import (
    apply_external_result,create_identity_case,identity_case_options,
    list_identity_cases,owner_review_identity_case,
)
from .routes import audit
from .security import login_required,owner_required

bp=Blueprint("identity_verification",__name__)


@bp.route("/identity-verification",methods=("GET","POST"))
@login_required
def identity_page():
    if request.method=="POST":
        try:
            item=create_identity_case(g.user,request.form)
            audit("create","identity_verification_case",str(item["id"]),actor=g.user)
            flash("Identity verification case created. Full identity numbers were not stored.","success")
        except (ValueError,LookupError,PermissionError) as exc:
            flash(str(exc),"error")
        return redirect(url_for("identity_verification.identity_page"))
    return render_template("identity_verification.html",cases=list_identity_cases(g.user),options=identity_case_options())


@bp.route("/admin/identity-verification",methods=("GET","POST"))
@login_required
@owner_required
def identity_admin_page():
    if request.method=="POST":
        try:
            item=owner_review_identity_case(
                g.user,int(request.form.get("case_id") or 0),decision=request.form.get("decision"),
                evidence_reference=request.form.get("evidence_reference"),note=request.form.get("note"),
            )
            audit("review","identity_verification_case",str(item["id"]),actor=g.user)
            flash("Identity evidence review recorded.","success")
        except (ValueError,LookupError,PermissionError) as exc:
            flash(str(exc),"error")
        return redirect(url_for("identity_verification.identity_admin_page"))
    return render_template("identity_verification_admin.html",cases=list_identity_cases(g.user,limit=300),options=identity_case_options())


@bp.post("/api/v1/ekyc/webhook")
def ekyc_webhook():
    raw=request.get_data(cache=True)
    payload=request.get_json(silent=True) or {}
    try:
        item=apply_external_result(payload,raw,request.headers.get("X-ZENDOC-EKYC-Signature",""))
        return jsonify({"accepted":True,"case_uid":item["case_uid"],"status":item["status"],
                        "external_ekyc_verified":item["status"]=="verified_external"})
    except PermissionError as exc:
        return jsonify({"error":{"code":403,"message":str(exc)}}),403
    except (ValueError,LookupError) as exc:
        return jsonify({"error":{"code":400,"message":str(exc)}}),400
