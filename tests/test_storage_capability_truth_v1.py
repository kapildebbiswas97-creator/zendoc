from zendoc.capability_registry import get_capability_registry


def test_s3_capability_uses_canonical_environment_names(monkeypatch):
    monkeypatch.setenv("ZENDOC_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("ZENDOC_S3_BUCKET", "zendoc-test")
    monkeypatch.setenv("ZENDOC_S3_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("ZENDOC_S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("ZENDOC_STORAGE_VERIFIED", raising=False)

    registry = get_capability_registry()
    assert registry["object_storage"]["status"] == "BETA"
    assert registry["community_media_public_durability"]["status"] == "INTEGRATION_REQUIRED"

    monkeypatch.setenv("ZENDOC_STORAGE_VERIFIED", "true")
    registry = get_capability_registry()
    assert registry["object_storage"]["status"] == "WORKING"
    assert registry["community_media_public_durability"]["status"] == "BETA"


def test_selected_s3_without_credentials_is_not_reported_working(monkeypatch):
    monkeypatch.setenv("ZENDOC_STORAGE_PROVIDER", "s3")
    for key in ("ZENDOC_S3_BUCKET", "ZENDOC_S3_ACCESS_KEY_ID", "ZENDOC_S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("ZENDOC_STORAGE_VERIFIED", raising=False)

    registry = get_capability_registry()
    assert registry["object_storage"]["status"] == "INTEGRATION_REQUIRED"
