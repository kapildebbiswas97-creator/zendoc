# ZENDOC State Geography Bootstrap — West Bengal, Assam, Uttar Pradesh

This workflow loads official LGD-style state geography into ZENDOC without fabricating missing locations.

## Target states

- West Bengal — LGD state code `19`
- Assam — LGD state code `18`
- Uttar Pradesh — LGD state code `9`

## Supported hierarchy

Primary administrative hierarchy:

```
India
└── State
    └── District
        └── Sub-district / Tehsil / Revenue Circle / Subdivision
            └── Village
```

Additional sourced geography relationships are stored separately:

- development block membership;
- Gram Panchayat membership;
- village → Gram Panchayat mapping;
- urban local-body membership.

This separation is intentional because block, revenue, panchayat, and urban boundaries are not always the same hierarchy.

## Official source strategy

Prefer Local Government Directory (LGD) / official government downloads for:

1. districts;
2. sub-districts;
3. development blocks;
4. local bodies;
5. Gram Panchayats where supplied;
6. villages;
7. village ↔ Gram Panchayat mappings.

Every record should retain:

- official source code;
- source name;
- snapshot/update date;
- state code;
- parent official code.

Never create a village or parent mapping just because a name looks similar.

## Canonical input fields

### District

```json
{
  "state_code": "19",
  "code": "official_district_code",
  "name": "District Name"
}
```

### Sub-district

```json
{
  "state_code": "19",
  "code": "official_subdistrict_code",
  "name": "Sub-district Name",
  "district_code": "official_district_code"
}
```

### Development block

```json
{
  "state_code": "19",
  "code": "official_block_code",
  "name": "Block Name",
  "district_code": "official_district_code",
  "subdistrict_code": "optional_official_subdistrict_code"
}
```

### Gram Panchayat

```json
{
  "state_code": "19",
  "code": "official_panchayat_code",
  "name": "Gram Panchayat Name",
  "district_code": "official_district_code",
  "block_code": "official_block_code"
}
```

### Village

```json
{
  "state_code": "19",
  "code": "official_village_code",
  "name": "Village Name",
  "district_code": "official_district_code",
  "subdistrict_code": "official_subdistrict_code",
  "block_code": "optional_official_block_code",
  "panchayat_code": "optional_official_panchayat_code"
}
```

## API

### List configured target states

`GET /api/v1/admin/ingestion/geography-targets`

Owner only.

### Preview a state bootstrap

`POST /api/v1/admin/ingestion/geography/<state_slug>/bootstrap`

Do not send `apply=true`.

Example state slugs:

- `west_bengal`
- `assam`
- `uttar_pradesh`

Preview validates:

- target state code;
- duplicate codes;
- required fields;
- payload size.

Preview does not create geography.

### Apply

Send:

```json
{
  "apply": true,
  "source": "lgd",
  "freshness_at": "2026-09-01T00:00:00+00:00",
  "districts": [],
  "subdistricts": [],
  "blocks": [],
  "panchayats": [],
  "local_bodies": [],
  "villages": [],
  "village_panchayat_links": []
}
```

Always preview the exact batch before apply.

### Coverage summary

`GET /api/v1/admin/ingestion/geography/<state_slug>/coverage`

Returns loaded counts for:

- district;
- subdivision/sub-district;
- block;
- panchayat;
- municipality/city/town;
- village;
- relationship counts.

## Recommended full-state import sequence

For each state:

1. load all districts;
2. load all sub-districts;
3. load development blocks;
4. load Gram Panchayats/local bodies;
5. load villages;
6. load village↔panchayat mapping;
7. inspect state coverage summary;
8. compare ZENDOC counts against the official source snapshot.

Do not load villages first.

## Large-state batching

The service accepts large state payloads, but the safest production method is chunked ingestion.

Recommended:

- districts: one state batch;
- sub-districts: one state batch;
- blocks/panchayats: one state batch or district chunks;
- villages: district-by-district or bounded chunks.

For Uttar Pradesh in particular, avoid one extremely large client request containing all locality rows. Use district chunks to reduce retry cost and make source reconciliation easier.

## Dibrugarh / Assam competition use

For a Dibrugarh competition deployment:

1. load the complete Assam administrative hierarchy;
2. verify Dibrugarh district/sub-district/village coverage;
3. prioritize Dibrugarh provider-directory ingestion;
4. onboard local hospitals, labs, pharmacies and doctors separately;
5. collect live slots/stock/prices only through provider refresh or partner workflows.

Official geography does not prove healthcare service availability.

## West Bengal pilot

For the home-state pilot:

1. load full West Bengal LGD hierarchy;
2. prioritize provider-directory coverage for Nadia and nearby districts;
3. preserve statewide search even if real-time provider coverage begins locally;
4. expand live provider operations district by district.

## Uttar Pradesh

Use full official state geography, but phase operational/provider data district-by-district.

A large geography directory is useful for discovery and future expansion, but ZENDOC should not claim live services merely because a locality exists in the graph.

## Truthfulness rule

A geography node means:

> an official/sourced location exists.

It does **not** mean:

- a hospital is present;
- a doctor is available;
- medicine stock exists;
- a lab slot exists;
- ambulance coverage exists;
- ZENDOC has a partner in that locality.

Those remain separate provider/entity and operational-data layers.
