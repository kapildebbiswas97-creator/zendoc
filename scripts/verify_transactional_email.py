#!/usr/bin/env python3
"""Send one real ZENDOC transactional-email smoke message.

On success, set ZENDOC_EMAIL_VERIFIED=true only for the unchanged SMTP
configuration that was tested.
"""
from __future__ import annotations

import argparse
import sys

from zendoc import create_app
from zendoc.email_delivery import email_delivery_status, send_transactional_email


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipient", help="Email address that you control for the delivery test")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        status = email_delivery_status()
        print("Email configuration:", status)
        if not status.get("transactional_email"):
            print("FAIL: SMTP transactional delivery is not configured.", file=sys.stderr)
            return 2
        try:
            result = send_transactional_email(
                args.recipient,
                "ZENDOC transactional email verification",
                (
                    "This is a real ZENDOC launch-readiness email smoke test.\n\n"
                    "If you received this message, SMTP accepted the delivery request. "
                    "Also verify that the message arrived in the intended mailbox before marking email verified."
                ),
            )
        except Exception as exc:
            print(f"FAIL: SMTP send failed: {exc}", file=sys.stderr)
            return 1
        print("SMTP transaction accepted:", result)
        print("Verify inbox delivery, then set ZENDOC_EMAIL_VERIFIED=true for this unchanged SMTP configuration.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
