# ZENDOC Healthcare Finder And Provider Network

Milestone 3 connects ZENDOC guidance to healthcare action without fabricating real-world provider data.

## Architecture

- `zendoc.healthcare_finder`: query normalization, cache, registered provider search, external provider fallback.
- `zendoc.places_provider`: provider interface for future Google Places or other map providers.
- `zendoc.provider_service`: provider profiles, specialties, schedules, slot generation, and connected booking.

## Current Data Sources

1. Verified ZENDOC provider profiles stored in the database.
2. External places provider abstraction.

If no places API key is configured, ZENDOC returns a graceful unavailable message and never invents doctors, hospitals, clinics, pharmacies, ratings, or opening hours.

## Location Privacy

Browser geolocation is requested only when the user presses "Use My Location". Manual city/area/PIN/address search is supported. Precise location is not persisted by this milestone.

## Provider Verification

Provider profiles default to `pending`. Admins can set:

- `pending`
- `verified`
- `rejected`
- `suspended`

Only verified providers appear in public registered-provider search and connected booking.

## Appointment Lifecycle

Connected appointments preserve the existing statuses:

- `requested`
- `confirmed`
- `completed`
- `cancelled`

Provider schedules generate slots. Booked requested/confirmed slots are excluded to prevent double booking.
