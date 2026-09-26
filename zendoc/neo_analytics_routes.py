"""Owner-only aggregate analytics contract for Neo/Plotly surfaces.

This module intentionally exposes only aggregate, non-clinical operational
metrics. It must not return raw medical records, symptom text, prompts,
messages, or patient-level clinical content.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .pilot_analytics import pilot_scorecard
from .security import owner_required
from .startup_analytics import (
    care_journey_conversion,
    india_coverage_quality,
    provider_onboarding_funnel,
    retention_metrics,
    startup_metrics,
    user_activation_funnel,
)


bp = Blueprint("neo_analytics", __name__)


def _bounded_days(value, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


@bp.get("/api/v1/admin/neo/analytics")
@owner_required
def neo_analytics_overview():
    """Return the stable aggregate contract consumed by Neo/Plotly clients."""
    days = _bounded_days(request.args.get("days"), default=30, maximum=365)
    provider_days = _bounded_days(
        request.args.get("provider_days"),
        default=90,
        maximum=365,
    )

    return jsonify(
        {
            "status": "OK",
            "contract": {
                "name": "zendoc.neo.analytics",
                "version": "1.0",
                "aggregate_only": True,
                "clinical_content": False,
            },
            "window_days": days,
            "startup": startup_metrics(g.user, days=days),
            "activation": user_activation_funnel(g.user, days=days),
            "coverage": india_coverage_quality(g.user),
            "retention": retention_metrics(g.user),
            "care_journey": care_journey_conversion(g.user, days=days),
            "provider_onboarding": provider_onboarding_funnel(
                g.user,
                days=provider_days,
            ),
            "pilot": pilot_scorecard(),
            "truth_notice": (
                "This endpoint contains aggregate ZENDOC operational evidence only. "
                "It excludes raw patient clinical content and must not be presented "
                "as clinical efficacy, diagnosis quality, or partner-authoritative "
                "outcomes unless separately verified."
            ),
        }
    )
