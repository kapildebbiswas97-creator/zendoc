"""Invoice and payment web/API routes."""
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .payments import (
    create_checkout_order,
    create_invoice,
    list_billable_resources,
    list_invoices,
    payment_gateway_status,
    verify_client_signature,
    verify_webhook,
)
from .routes import audit, require_api_user
from .security import login_required

bp = Blueprint("payments", __name__)


@bp.route("/payments", methods=("GET", "POST"))
@login_required
def payments_page():
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "issue_invoice":
                invoice = create_invoice(
                    g.user,
                    resource_ref=request.form.get("resource_ref"),
                    amount_inr=request.form.get("amount_inr"),
                    description=request.form.get("description"),
                )
                audit("create", "care_invoice", str(invoice["id"]))
                flash("Invoice issued to the connected patient.", "success")
            else:
                raise ValueError("Unsupported payment action.")
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("payments.payments_page"))

    resources = []
    if g.user["role"] in {"doctor", "hospital", "pharmacy"}:
        try:
            resources = list_billable_resources(g.user)
        except PermissionError as exc:
            flash(str(exc), "warning")
    return render_template(
        "payments.html",
        invoices=list_invoices(g.user),
        billable_resources=resources,
        gateway=payment_gateway_status(),
    )


@bp.post("/payments/checkout/<int:invoice_id>")
@login_required
def checkout(invoice_id):
    try:
        checkout_data = create_checkout_order(g.user, invoice_id)
        audit("start", "payment_checkout", str(invoice_id))
        return render_template(
            "payment_checkout.html",
            checkout=checkout_data,
            gateway=payment_gateway_status(),
        )
    except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("payments.payments_page"))


@bp.post("/payments/verify/<int:invoice_id>")
@login_required
def verify_checkout(invoice_id):
    try:
        invoice = verify_client_signature(
            g.user,
            invoice_id,
            order_id=request.form.get("razorpay_order_id"),
            payment_id=request.form.get("razorpay_payment_id"),
            signature=request.form.get("razorpay_signature"),
        )
        audit("verify", "payment_checkout", str(invoice_id))
        flash(
            "Payment signature verified. Final paid status waits for the signed gateway capture webhook.",
            "success",
        )
    except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("payments.payments_page"))


@bp.post("/api/v1/payments/webhook/razorpay")
def razorpay_webhook():
    try:
        result = verify_webhook(
            request.get_data(cache=False),
            request.headers.get("X-Razorpay-Signature", ""),
        )
        return jsonify(result)
    except PermissionError as exc:
        return jsonify({"error": {"code": 401, "message": str(exc)}}), 401
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400


@bp.get("/api/v1/payments/invoices")
def api_invoices():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"invoices": list_invoices(user), "gateway": payment_gateway_status()})


@bp.post("/api/v1/payments/invoices")
def api_create_invoice():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        invoice = create_invoice(
            user,
            resource_ref=data.get("resource_ref"),
            amount_inr=data.get("amount_inr"),
            description=data.get("description"),
        )
        audit("create", "care_invoice", str(invoice["id"]), actor=user)
        return jsonify({"invoice": invoice}), 201
    except PermissionError as exc:
        return jsonify({"error": {"code": 403, "message": str(exc)}}), 403
    except (ValueError, LookupError) as exc:
        return jsonify({"error": {"code": 400, "message": str(exc)}}), 400
