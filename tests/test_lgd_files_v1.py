from zendoc.lgd_files import normalize_lgd_bundle, parse_delimited_text


def test_parse_realistic_lgd_semicolon_csv():
    text = (
        "S.No.;State Code;State Name (In English);District Code;District Name(In English);"
        "Sub-District Code;Sub-District Name;Village Code;Village Name (In Englsih)\n"
        "1;19;WEST BENGAL;320;NADIA;2320;Ranaghat;123456;Pilot Village\n"
    )
    rows = parse_delimited_text(text)
    assert rows[0]["State Code"] == "19"
    assert rows[0]["Village Name (In Englsih)"] == "Pilot Village"


def test_normalizer_filters_only_target_state_and_preserves_admin_codes():
    districts = [
        {"State Code": "19", "District Code": "320", "District Name(In English)": "NADIA"},
        {"State Code": "18", "District Code": "999", "District Name(In English)": "OTHER"},
    ]
    subdistricts = [
        {
            "State Code": "19",
            "District Code": "320",
            "Sub-District Code": "2320",
            "Sub-District Name": "Ranaghat",
        }
    ]
    villages = [
        {
            "State Code": "19",
            "District Code": "320",
            "Sub-District Code": "2320",
            "Village Code": "123456",
            "Village Name (In Englsih)": "Pilot Village",
        }
    ]

    bundle = normalize_lgd_bundle(
        state_code="19",
        districts=districts,
        subdistricts=subdistricts,
        villages=villages,
    )

    assert bundle["districts"] == [{"state_code": "19", "code": "320", "name": "NADIA"}]
    assert bundle["subdistricts"][0]["district_code"] == "320"
    assert bundle["villages"][0]["subdistrict_code"] == "2320"


def test_villages_by_blocks_adds_block_panchayat_and_membership_codes():
    villages = [
        {
            "State Code": "19",
            "District Code": "306",
            "Sub-District Code": "2278",
            "Village Code": "319067",
            "Village Name (In Englsih)": "Taldanga",
        }
    ]
    mappings = [
        {
            "State code": "19",
            "District code": "306",
            "Subdistrict code": "2278",
            "Village code": "319067",
            "Village Name(In English)": "Taldanga",
            "Localbody Code": "108657",
            "Localbody Name(In English)": "PALIGRAM",
            "Block code": "2815",
            "Block Name(In English)": "MANGOLKOTE",
        }
    ]

    bundle = normalize_lgd_bundle(
        state_code="19",
        villages=villages,
        villages_by_blocks=mappings,
    )

    assert bundle["blocks"][0]["code"] == "2815"
    assert bundle["panchayats"][0]["code"] == "108657"
    assert bundle["villages"][0]["block_code"] == "2815"
    assert bundle["villages"][0]["panchayat_code"] == "108657"
    assert bundle["village_panchayat_links"][0]["village_code"] == "319067"


def test_assam_and_up_state_codes_are_filterable():
    rows = [
        {"State Code": "18", "District Code": "AS1", "District Name(In English)": "DIBRUGARH"},
        {"State Code": "9", "District Code": "UP1", "District Name(In English)": "LUCKNOW"},
    ]
    assam = normalize_lgd_bundle(state_code="18", districts=rows)
    up = normalize_lgd_bundle(state_code="9", districts=rows)

    assert [row["name"] for row in assam["districts"]] == ["DIBRUGARH"]
    assert [row["name"] for row in up["districts"]] == ["LUCKNOW"]
