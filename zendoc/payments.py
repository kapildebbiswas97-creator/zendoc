"""Provider-issued invoice and Razorpay payment boundary for ZENDOC.

No payment is represented as paid merely because checkout opened or a client
callback fired. Client signatures are verified first; final paid state requires
a valid gateway webhook such as payment.captured or order.paid.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .db import get_db, now_iso


SUPPORTED_GATEWAY = "razorpay"


def ensure_payment_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS care_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_uid TEXT NOT NULL UNIQUE,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            payee_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            amount_paise INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'issued',
            gateway TEXT,
            gateway_order_id TEXT UNIQUE,
            gateway_payment_id TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            paid_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_care_invoices_patient
            ON care_invoices(patient_id,status,created_at);
        CREATE INDEX IF NOT EXISTS idx_care_invoices_payee
            ON care_invoices(payee_user_id,status,created_at);

        CREATE TABLE IF NOT EXISTS payment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL REFERENCES care_invoices(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            provider_event_ref TEXT,
            signature_verified INTEGER NOT NULL DEFAULT 0,
            payload_digest TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_payment_events_invoice
            ON payment_events(invoice_id,created_at,id);
        """
    )


def payment_gateway_status() -> dict:
    key_id = str(os.environ.get("ZENDOC_RAZORPAY_KEY_ID") or "").strip()
    key_secret = str(os.environ.get("ZENDOC_RAZORPAY_KEY_SECRET") or "").strip()
    webhook_secret = str(os.environ.get("ZENDOC_RAZORPAY_WEBHOOK_SECRET") or "").strip()
    return {
        "gateway": SUPPORTED_GATEWAY,
        "checkout_configured": bool(key_id and key_secret),
        "webhook_configured": bool(webhook_secret),
        "ready_for_live_payment": bool(key_id and key_secret and webhook_secret),
        "key_id": key_id if key_id and key_secret and webhook_secret else "",
        "truth_notice": (
            "Direct payment is enabled only when Razorpay checkout credentials and webhook verification are configured. "
            "Opening checkout or receiving an unsigned callback never marks an invoice paid."
        ),
    }


def _actor_id(user) -> int:
    return int(user["id"])


def _amount_to_paise(value) -> int:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid invoice amount.")
    if amount <= 0:
        raise ValueError("Invoice amount must be greater than zero.")
    if amount > Decimal("1000000.00"):
        raise ValueError("Invoice amount exceeds the supported ZENDOC checkout limit.")
    return int(amount * 100)


def _verified_payee(actor) -> dict:
    if str(actor["role"]) not in {"doctor", "hospital", "pharmacy"}:
        raise PermissionError("Only verified doctor, hospital or pharmacy accounts can issue care invoices.")
    row = get_db().execute(
        """
        SELECT p.*,u.name account_name,u.role
        FROM provider_profiles p JOIN users u ON u.id=p.user_id
        WHERE p.user_id=? AND u.active=1 AND p.verification_status='verified'
        """,
        (_actor_id(actor),),
    ).fetchone()
    if not row:
        raise PermissionError("Provider verification is required before issuing a payment invoice.")
    return dict(row)


def list_billable_resources(actor) -> list[dict]:
    _verified_payee(actor)
    uid = _actor_id(actor)
    resources = []
    if str(actor["role"]) in {"doctor", "hospital"}:
        rows = get_db().execute(
            """
            SELECT a.id,a.patient_id,a.provider_name,a.scheduled_for,a.status,u.name patient_name
            FROM appointments a JOIN users u ON u.id=a.patient_id
            WHERE a.provider_id=? AND a.status IN ('requested','confirmed','completed')
            ORDER BY a.created_at DESC LIMIT 100
            """,
            (uid,),
        ).fetchall()
        for row in rows:
            resources.append({
                "ref": f"appointment:{row['id']}",
                "type": "appointment",
                "resource_id": int(row["id"]),
                "patient_id": int(row["patient_id"]),
                "patient_name": row["patient_name"],
                "title": f"Appointment · {row['scheduled_for']} · {row['status']}",
            })
    if str(actor["role"]) == "pharmacy":
        rows = get_db().execute(
            """
            SELECT o.id,o.patient_id,o.status,o.created_at,u.name patient_name
            FROM medicine_orders o JOIN users u ON u.id=o.patient_id
            WHERE o.pharmacy_id=? AND o.status NOT IN ('cancelled','rejected')
            ORDER BY o.created_at DESC LIMIT 100
            """,
            (uid,),
        ).fetchall()
        for row in rows:
            resources.append({
                "ref": f"medicine_order:{row['id']}",
                "type": "medicine_order",
                "resource_id": int(row["id"]),
                "patient_id": int(row["patient_id"]),
                "patient_name": row["patient_name"],
                "title": f"Pharmacy request #{row['id']} · {row['status']}",
            })
    return resources


def _resolve_resource(actor, resource_ref: str) -> tuple[str, int, int]:
    _verified_payee(actor)
    raw = str(resource_ref or "").strip()
    if ":" not in raw:
        raise ValueError("Choose a connected billable care item.")
    kind, raw_id = raw.split(":", 1)
    try:
        rid = int(raw_id)
    except ValueError:
        raise ValueError("Invalid billable care item.")
    uid = _actor_id(actor)
    if kind == "appointment" and str(actor["role"]) in {"doctor", "hospital"}:
        row = get_db().execute(
            """
            SELECT patient_id FROM appointments
            WHERE id=? AND provider_id=? AND status IN ('requested','confirmed','completed')
            """,
            (rid, uid),
        ).fetchone()
    elif kind == "medicine_order" and str(actor["role"]) == "pharmacy":
        row = get_db().execute(
            """
            SELECT patient_id FROM medicine_orders
            WHERE id=? AND pharmacy_id=? AND status NOT IN ('cancelled','rejected')
            """,
            (rid, uid),
        ).fetchone()
    else:
        row = None
    if not row:
        raise PermissionError("This care item is not billable by the signed-in verified provider.")
    return kind, rid, int(row["patient_id"])


def create_invoice(actor, *, resource_ref: str, amount_inr, description: str) -> dict:
    ensure_payment_schema()
    kind, rid, patient_id = _resolve_resource(actor, resource_ref)
    existing = get_db().execute(
        """
        SELECT id FROM care_invoices
        WHERE payee_user_id=? AND resource_type=? AND resource_id=?
          AND status IN ('issued','checkout_ready','client_verified')
        ORDER BY id DESC LIMIT 1
        """,
        (_actor_id(actor), kind, rid),
    ).fetchone()
    if existing:
        raise ValueError("An open invoice already exists for this care item.")
    description = " ".join(str(description or "").strip().split())[:300]
    if not description:
        raise ValueError("Invoice description is required.")
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO care_invoices
        (invoice_uid,patient_id,payee_user_id,resource_type,resource_id,amount_paise,currency,
         description,status,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,'INR',?,'issued',?,?,?)
        """,
        (
            f"inv_{uuid.uuid4().hex}",
            patient_id,
            _actor_id(actor),
            kind,
            rid,
            _amount_to_paise(amount_inr),
            description,
            _actor_id(actor),
            now,
            now,
        ),
    )
    get_db().commit()
    return get_invoice(actor, int(cursor.lastrowid))


PAYMENT_STATUS_STEPS = (
    ("issued", "Invoice issued", "The verified provider created a charge tied to a connected care item."),
    ("checkout_ready", "Checkout ready", "A real gateway order exists and the billed patient can open secure checkout."),
    ("client_verified", "Checkout signature verified", "The browser checkout signature matched. This is not final payment confirmation."),
    ("paid", "Payment confirmed", "A signed gateway capture webhook confirmed the paid state."),
)


def _invoice_status_meta(status: str) -> dict:
    current = str(status or "issued").strip().lower()
    order = [step[0] for step in PAYMENT_STATUS_STEPS]
    current_index = order.index(current) if current in order else -1
    steps = []
    for index, (key, label, explanation) in enumerate(PAYMENT_STATUS_STEPS):
        steps.append(
            {
                "key": key,
                "label": label,
                "explanation": explanation,
                "complete": bool(current_index >= index and current_index >= 0),
                "current": bool(current == key),
            }
        )
    if current in order:
        label = PAYMENT_STATUS_STEPS[current_index][1]
        explanation = PAYMENT_STATUS_STEPS[current_index][2]
    else:
        label = current.replace("_", " ").title() or "Unknown"
        explanation = "This invoice is in a non-standard state. ZENDOC will not infer payment completion."
    return {
        "key": current,
        "label": label,
        "explanation": explanation,
        "steps": steps,
        "final_paid": current == "paid",
    }


def _display_provider_ref(value) -> str | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    if len(clean) <= 14:
        return clean
    return f"{clean[:7]}…{clean[-4:]}"


def _invoice_events(invoice_id: int) -> list[dict]:
    rows = get_db().execute(
        """
        SELECT event_type,provider_event_ref,signature_verified,payload_digest,created_at
        FROM payment_events
        WHERE invoice_id=?
        ORDER BY created_at ASC,id ASC
        """,
        (int(invoice_id),),
    ).fetchall()
    return [
        {
            "event_type": row["event_type"],
            "provider_event_ref": _display_provider_ref(row["provider_event_ref"]),
            "signature_verified": bool(row["signature_verified"]),
            "payload_digest_prefix": str(row["payload_digest"] or "")[:12],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_invoice(user, invoice_id: int) -> dict:
    ensure_payment_schema()
    uid = _actor_id(user)
    row = get_db().execute(
        """
        SELECT i.*,p.name patient_name,payee.name payee_name,payee.role payee_role
        FROM care_invoices i
        JOIN users p ON p.id=i.patient_id
        JOIN users payee ON payee.id=i.payee_user_id
        WHERE i.id=? AND (i.patient_id=? OR i.payee_user_id=?)
        """,
        (int(invoice_id), uid, uid),
    ).fetchone()
    if not row:
        raise LookupError("Invoice not found.")
    item = dict(row)
    item["amount_inr"] = f"{int(item['amount_paise']) / 100:.2f}"
    item["status_meta"] = _invoice_status_meta(item.get("status"))
    item["events"] = _invoice_events(int(item["id"]))
    return item


def list_invoices(user, *, limit=100) -> list[dict]:
    ensure_payment_schema()
    uid = _actor_id(user)
    rows = get_db().execute(
        """
        SELECT i.id FROM care_invoices i
        WHERE i.patient_id=? OR i.payee_user_id=?
        ORDER BY i.created_at DESC,i.id DESC LIMIT ?
        """,
        (uid, uid, max(1, min(int(limit or 100), 200))),
    ).fetchall()
    return [get_invoice(user, int(row["id"])) for row in rows]


def _razorpay_request(path: str, payload: dict) -> dict:
    status = payment_gateway_status()
    if not status["ready_for_live_payment"]:
        raise RuntimeError("Razorpay checkout and webhook verification are not fully configured.")
    key_id = os.environ["ZENDOC_RAZORPAY_KEY_ID"]
    key_secret = os.environ["ZENDOC_RAZORPAY_KEY_SECRET"]
    auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    req = Request(
        f"https://api.razorpay.com/v1/{path.lstrip('/')}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Payment gateway order creation failed safely; no invoice was marked paid.") from exc
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Payment gateway returned an invalid order response.")
    return data


def create_checkout_order(patient, invoice_id: int) -> dict:
    ensure_payment_schema()
    invoice = get_invoice(patient, invoice_id)
    if int(invoice["patient_id"]) != _actor_id(patient):
        raise PermissionError("Only the billed patient can start checkout.")
    if invoice["status"] == "paid":
        raise ValueError("This invoice is already paid.")
    if invoice.get("gateway_order_id"):
        return {
            "invoice": invoice,
            "order_id": invoice["gateway_order_id"],
            "key_id": payment_gateway_status()["key_id"],
        }

    order = _razorpay_request(
        "orders",
        {
            "amount": int(invoice["amount_paise"]),
            "currency": invoice["currency"],
            "receipt": invoice["invoice_uid"][:40],
            "notes": {
                "zendoc_invoice_uid": invoice["invoice_uid"],
                "resource_type": invoice["resource_type"],
                "resource_id": str(invoice["resource_id"]),
            },
        },
    )
    get_db().execute(
        """
        UPDATE care_invoices
        SET gateway='razorpay',gateway_order_id=?,status='checkout_ready',updated_at=?
        WHERE id=?
        """,
        (str(order["id"])[:160], now_iso(), int(invoice_id)),
    )
    get_db().commit()
    return {
        "invoice": get_invoice(patient, invoice_id),
        "order_id": str(order["id"]),
        "key_id": payment_gateway_status()["key_id"],
    }


def verify_client_signature(patient, invoice_id: int, *, order_id: str, payment_id: str, signature: str) -> dict:
    ensure_payment_schema()
    invoice = get_invoice(patient, invoice_id)
    if int(invoice["patient_id"]) != _actor_id(patient):
        raise PermissionError("Only the billed patient can verify checkout.")
    if not invoice.get("gateway_order_id") or str(invoice["gateway_order_id"]) != str(order_id):
        raise PermissionError("Checkout order does not match this invoice.")
    secret = str(os.environ.get("ZENDOC_RAZORPAY_KEY_SECRET") or "")
    if not secret:
        raise RuntimeError("Payment signature verification is not configured.")
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(signature or "")):
        raise PermissionError("Payment signature verification failed.")
    now = now_iso()
    get_db().execute(
        """
        UPDATE care_invoices
        SET gateway_payment_id=?,status='client_verified',updated_at=?
        WHERE id=? AND status<>'paid'
        """,
        (str(payment_id)[:160], now, int(invoice_id)),
    )
    _record_event(int(invoice_id), "checkout_signature_verified", str(payment_id), True, b"client-signature")
    get_db().commit()
    return get_invoice(patient, invoice_id)


def verify_webhook(raw_body: bytes, signature: str) -> dict:
    ensure_payment_schema()
    secret = str(os.environ.get("ZENDOC_RAZORPAY_WEBHOOK_SECRET") or "")
    if not secret:
        raise RuntimeError("Razorpay webhook verification is not configured.")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(signature or "")):
        raise PermissionError("Invalid Razorpay webhook signature.")
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Razorpay webhook payload.") from exc

    event_type = str(event.get("event") or "")
    payload = event.get("payload") or {}
    payment_entity = ((payload.get("payment") or {}).get("entity") or {})
    order_entity = ((payload.get("order") or {}).get("entity") or {})
    order_id = str(payment_entity.get("order_id") or order_entity.get("id") or "")
    payment_id = str(payment_entity.get("id") or "")
    if event_type not in {"payment.captured", "order.paid"} or not order_id:
        return {"accepted": True, "handled": False, "event": event_type}

    row = get_db().execute(
        """
        SELECT id,amount_paise,currency,status FROM care_invoices
        WHERE gateway='razorpay' AND gateway_order_id=?
        """,
        (order_id,),
    ).fetchone()
    if not row:
        return {"accepted": True, "handled": False, "event": event_type}

    expected_amount = int(row["amount_paise"])
    expected_currency = str(row["currency"] or "INR").upper()
    observed_amount = payment_entity.get("amount")
    if observed_amount in (None, ""):
        observed_amount = order_entity.get("amount_paid")
    observed_currency = str(
        payment_entity.get("currency") or order_entity.get("currency") or expected_currency
    ).upper()

    if observed_amount not in (None, "") and int(observed_amount) != expected_amount:
        raise PermissionError("Signed payment event amount does not match the ZENDOC invoice.")
    if observed_currency != expected_currency:
        raise PermissionError("Signed payment event currency does not match the ZENDOC invoice.")
    if event_type == "payment.captured" and str(payment_entity.get("status") or "").lower() not in {"captured", ""}:
        raise PermissionError("Payment event is not in captured state.")
    if event_type == "order.paid" and str(order_entity.get("status") or "").lower() not in {"paid", ""}:
        raise PermissionError("Order event is not in paid state.")

    invoice_id = int(row["id"])
    now = now_iso()
    get_db().execute(
        """
        UPDATE care_invoices
        SET status='paid',gateway_payment_id=COALESCE(NULLIF(?,''),gateway_payment_id),
            paid_at=COALESCE(paid_at,?),updated_at=?
        WHERE id=?
        """,
        (payment_id, now, now, invoice_id),
    )
    _record_event(invoice_id, event_type, payment_id or order_id, True, raw_body)
    get_db().commit()
    return {"accepted": True, "handled": True, "event": event_type, "invoice_id": invoice_id}


def _record_event(invoice_id: int, event_type: str, ref: str, verified: bool, raw_body: bytes):
    digest = hashlib.sha256(raw_body).hexdigest()
    get_db().execute(
        """
        INSERT INTO payment_events
        (invoice_id,event_type,provider_event_ref,signature_verified,payload_digest,created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (int(invoice_id), str(event_type)[:120], str(ref or "")[:200] or None, 1 if verified else 0, digest, now_iso()),
    )
