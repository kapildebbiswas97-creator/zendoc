from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc import create_app
from zendoc.db import get_db
from zendoc.medical_knowledge_documents import register_medical_knowledge_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Register one governed RAG artifact for owner review.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--published", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--usage-basis", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    path = Path(args.input)
    try:
        payload = path.read_bytes()
    except OSError:
        print("Artifact could not be read.", file=sys.stderr)
        return 2
    if not payload:
        print("Artifact is empty.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        owner_email = str(app.config.get("ADMIN_EMAIL") or "").strip().lower()
        owner = get_db().execute(
            "SELECT * FROM users WHERE email_normalized=? AND role='admin' AND active=1",
            (owner_email,),
        ).fetchone()
        if owner is None:
            print("Configured owner account is not active.", file=sys.stderr)
            return 3

        metadata = {
            "source_id": args.source_id,
            "document_title": args.title,
            "document_url": args.url,
            "publication_date": args.published,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content_sha256": hashlib.sha256(payload).hexdigest(),
            "usage_basis": args.usage_basis,
            "version": args.version,
        }
        try:
            document = register_medical_knowledge_document(owner, metadata)
        except (LookupError, PermissionError, ValueError) as exc:
            print(f"Registration blocked: {exc}", file=sys.stderr)
            return 4

    print(document["document_uid"])
    print(document["review_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
