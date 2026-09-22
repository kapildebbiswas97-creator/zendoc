from zendoc.record_storage import S3CompatibleRecordStorage
from tests.test_milestone1 import make_app


def test_custom_s3_endpoint_forces_path_style_sigv4(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    app.config.update(
        STORAGE_PROVIDER="s3_compatible",
        S3_BUCKET="zendoc-health-records",
        S3_ACCESS_KEY_ID="test-access",
        S3_SECRET_ACCESS_KEY="test-secret",
        S3_ENDPOINT_URL="https://namespace.compat.objectstorage.ap-mumbai-1.oci.customer-oci.com",
        S3_REGION="ap-mumbai-1",
        S3_SERVER_SIDE_ENCRYPTION="",
    )

    captured = {}

    def fake_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("boto3.client", fake_client)

    with app.app_context():
        _client, settings = S3CompatibleRecordStorage()._client()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"].startswith("https://")
    assert captured["config"].signature_version == "s3v4"
    assert captured["config"].s3["addressing_style"] == "path"
    assert settings["bucket"] == "zendoc-health-records"


def test_native_aws_s3_does_not_force_custom_endpoint_addressing(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    app.config.update(
        STORAGE_PROVIDER="s3",
        S3_BUCKET="zendoc-health-records",
        S3_ACCESS_KEY_ID="test-access",
        S3_SECRET_ACCESS_KEY="test-secret",
        S3_ENDPOINT_URL="",
        S3_REGION="ap-south-1",
        S3_SERVER_SIDE_ENCRYPTION="AES256",
    )

    captured = {}

    def fake_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("boto3.client", fake_client)

    with app.app_context():
        S3CompatibleRecordStorage()._client()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] is None
    assert "config" not in captured
