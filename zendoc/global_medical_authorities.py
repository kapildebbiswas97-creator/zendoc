GLOBAL_MEDICAL_AUTHORITIES = {
    "sg_moh_guidance": ("Ministry of Health, Singapore", "https://www.moh.gov.sg/", "singapore"),
    "uk_nice_guidance": ("National Institute for Health and Care Excellence", "https://www.nice.org.uk/guidance", "united_kingdom"),
    "uk_nhs_guidance": ("NHS", "https://www.nhs.uk/", "united_kingdom"),
    "us_cdc_guidance": ("Centers for Disease Control and Prevention", "https://www.cdc.gov/", "united_states"),
    "us_hhs_guidance": ("U.S. Department of Health and Human Services", "https://www.hhs.gov/", "united_states"),
    "ru_minzdrav_guidance": ("Ministry of Health of the Russian Federation", "https://minzdrav.gov.ru/", "russia"),
    "cn_nhc_guidance": ("National Health Commission of the People's Republic of China", "https://www.nhc.gov.cn/", "china"),
    "bd_dghs_guidance": ("Directorate General of Health Services, Bangladesh", "https://dghs.gov.bd/", "bangladesh"),
    "pk_nhsrc_guidance": ("Ministry of National Health Services, Regulations and Coordination, Pakistan", "https://www.nhsrc.gov.pk/", "pakistan"),
}


def install_global_medical_authorities(registry):
    for source_id, (publisher, url, jurisdiction) in GLOBAL_MEDICAL_AUTHORITIES.items():
        registry.setdefault(source_id, {
            "source_id": source_id,
            "publisher": publisher,
            "canonical_url": url,
            "jurisdiction": jurisdiction,
            "source_kind": "national_health_guidance",
            "trust_tier": "PRIMARY_AUTHORITY",
            "source_status": "DISCOVERY_APPROVED",
            "ingestion_status": "REVIEW_REQUIRED",
            "allowed_for_discovery": True,
            "allowed_for_answering_without_snapshot": False,
            "requires_document_level_usage_review": True,
            "requires_version_and_publication_date": True,
            "notes": "Discovery/review source family only; concrete documents still require snapshot provenance and owner approval.",
        })
