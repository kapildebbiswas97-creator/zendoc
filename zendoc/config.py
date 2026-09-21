import os
import re
from datetime import timedelta
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default, minimum=1, maximum=120):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _sqlite_path_from_url(database_url, base_dir):
    raw_path = database_url[len("sqlite:///") :]
    if raw_path == ":memory:":
        return raw_path
    raw_path = os.path.expandvars(os.path.expanduser(raw_path))
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", raw_path):
        raw_path = raw_path[1:]
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(base_dir) / path
    return str(path.resolve())


def resolve_database_config(base_dir, env, testing=False, overrides=None):
    """Resolve a database target without silently ignoring DATABASE_URL."""
    overrides = overrides or {}
    explicit_test_database = testing and bool(overrides.get("DATABASE"))
    database_url = str(
        overrides.get("DATABASE_URL")
        if "DATABASE_URL" in overrides
        else os.environ.get("DATABASE_URL", "")
    ).strip()
    if explicit_test_database:
        # A developer's DATABASE_URL must never redirect an isolated test run.
        database_url = ""

    default_path = Path(base_dir) / "instance" / "zendoc.db"
    configured_path = str(
        overrides.get("DATABASE")
        or os.environ.get("ZENDOC_DATABASE_PATH", "")
        or default_path
    ).strip()

    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://") :]
    if database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        engine = "postgresql"
        database_path = str(default_path)
        durability = "durable_configured"
    elif database_url.startswith("sqlite:///"):
        engine = "sqlite"
        database_path = _sqlite_path_from_url(database_url, base_dir)
        durability = "local_development"
    elif database_url:
        raise ConfigError(
            "Unsupported DATABASE_URL scheme. Use postgresql:// for managed PostgreSQL "
            "or sqlite:/// for a local SQLite database."
        )
    else:
        engine = "sqlite"
        database_path = configured_path
        durability = "local_development"

    persistence_mode = str(
        overrides.get("PERSISTENCE_MODE")
        or os.environ.get("ZENDOC_PERSISTENCE_MODE", "")
    ).strip().lower()
    persistence_verified = bool(
        overrides.get("PERSISTENCE_VERIFIED")
        if "PERSISTENCE_VERIFIED" in overrides
        else env_bool("ZENDOC_PERSISTENCE_VERIFIED", False)
    )

    if testing:
        durability = "isolated_testing"
    elif env == "production" and engine == "sqlite":
        if persistence_mode == "durable" and bool(os.environ.get("ZENDOC_DATABASE_PATH") or overrides.get("DATABASE")):
            durability = "durable_configured"
        else:
            durability = "integration_required"

    return {
        "DATABASE": database_path,
        "DATABASE_URL": database_url,
        "DATABASE_ENGINE": engine,
        "DATABASE_DURABILITY": durability,
        "PERSISTENCE_VERIFIED": persistence_verified,
    }


def load_config(base_dir, overrides=None):
    env = os.environ.get("ZENDOC_ENV", "development").strip().lower()
    testing = bool(overrides and overrides.get("TESTING"))
    secret_key = os.environ.get("ZENDOC_SECRET_KEY")
    if not secret_key and (env == "production" and not testing):
        raise ConfigError("ZENDOC_SECRET_KEY is required in production.")
    ai_provider = os.environ.get("ZENDOC_AI_PROVIDER", "").strip().lower()
    ai_base_url = os.environ.get(
        "ZENDOC_AI_BASE_URL", "https://api.openai.com" if ai_provider == "openai" else ""
    ).strip()

    database_config = resolve_database_config(base_dir, env, testing, overrides)
    connected_care_data_mode = str(
        (overrides or {}).get("CONNECTED_CARE_DATA_MODE")
        or os.environ.get("ZENDOC_CONNECTED_CARE_DATA_MODE", "LIVE")
    ).strip().upper()
    if connected_care_data_mode not in {"LIVE", "DEMO"}:
        raise ConfigError("ZENDOC_CONNECTED_CARE_DATA_MODE must be LIVE or DEMO.")
    config = {
        "ZENDOC_ENV": env,
        "SECRET_KEY": secret_key or "development-only-secret-key",
        "UPLOAD_FOLDER": str(base_dir / "uploads"),
        "DATABASE_BACKUP_DIR": str(
            Path(os.environ.get("ZENDOC_DATABASE_BACKUP_DIR", str(base_dir / "instance" / "backups"))).resolve()
        ),
        "MAX_CONTENT_LENGTH": int(os.environ.get("ZENDOC_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        "SESSION_COOKIE_NAME": "zendoc_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": env == "production",
        "SESSION_REFRESH_EACH_REQUEST": True,
        "PERMANENT_SESSION_LIFETIME": timedelta(
            hours=env_int("ZENDOC_SESSION_LIFETIME_HOURS", 12, minimum=1, maximum=24 * 30)
        ),
        "SESSION_IDLE_MINUTES": env_int(
            "ZENDOC_SESSION_IDLE_MINUTES", 120, minimum=5, maximum=24 * 60
        ),
        "ALLOW_LEGACY_GET_LOGOUT": env != "production",
        "PASSWORD_RECOVERY_MODE": os.environ.get(
            "ZENDOC_PASSWORD_RECOVERY_MODE", "integration_required" if env == "production" else "local_demo"
        ).strip().lower(),
        "ADMIN_EMAIL": os.environ.get("ZENDOC_ADMIN_EMAIL"),
        "ADMIN_PASSWORD": os.environ.get("ZENDOC_ADMIN_PASSWORD"),
        "CREATE_DEV_ADMIN": env != "production" and env_bool("ZENDOC_CREATE_DEV_ADMIN", True),
        "RATE_LIMIT_PER_MINUTE": int(os.environ.get("ZENDOC_RATE_LIMIT_PER_MINUTE", "120")),
        "AUTH_RATE_LIMIT_PER_MINUTE": env_int(
            "ZENDOC_AUTH_RATE_LIMIT_PER_MINUTE", 20, minimum=3, maximum=300
        ),
        "API_ACCESS_TOKEN_MINUTES": env_int(
            "ZENDOC_API_ACCESS_TOKEN_MINUTES", 60, minimum=5, maximum=1440
        ),
        "API_REFRESH_TOKEN_DAYS": env_int(
            "ZENDOC_API_REFRESH_TOKEN_DAYS", 30, minimum=1, maximum=180
        ),
        "OBSERVABILITY_RETENTION_DAYS": env_int(
            "ZENDOC_OBSERVABILITY_RETENTION_DAYS", 30, minimum=1, maximum=365
        ),
        "PLACES_PROVIDER": os.environ.get("ZENDOC_PLACES_PROVIDER", "none"),
        "VIDEO_PROVIDER": os.environ.get("ZENDOC_VIDEO_PROVIDER", "none"),
        "YOUTUBE_API_KEY": os.environ.get("ZENDOC_YOUTUBE_API_KEY", ""),
        "REQUIRE_DURABLE_DATABASE": env_bool("ZENDOC_REQUIRE_DURABLE_DATABASE", False),
        "BACKUP_VERIFIED": env_bool("ZENDOC_BACKUP_VERIFIED", False),
        "STORAGE_PROVIDER": os.environ.get("ZENDOC_STORAGE_PROVIDER", "local").strip().lower(),
        "STORAGE_VERIFIED": env_bool("ZENDOC_STORAGE_VERIFIED", False),
        "TELEHEALTH_PROVIDER": os.environ.get("ZENDOC_TELEHEALTH_PROVIDER", "internal_webrtc").strip().lower(),
        "REALTIME_PROVIDER": os.environ.get("ZENDOC_REALTIME_PROVIDER", "polling").strip().lower(),
        "NOTIFICATION_PROVIDER": os.environ.get("ZENDOC_NOTIFICATION_PROVIDER", "in_app").strip().lower(),
        "EKYC_PROVIDER": os.environ.get("ZENDOC_EKYC_PROVIDER", "none").strip().lower(),
        "EKYC_VERIFIED": env_bool("ZENDOC_EKYC_VERIFIED", False),
        "PUBLIC_BASE_URL": os.environ.get("ZENDOC_PUBLIC_BASE_URL", "").strip(),
        "PUBLIC_RELEASE_REQUIRED": env_bool("ZENDOC_PUBLIC_RELEASE_REQUIRED", False),
        "SUPPORT_EMAIL": os.environ.get("ZENDOC_SUPPORT_EMAIL", "").strip(),
        "EMAIL_PROVIDER": os.environ.get("ZENDOC_EMAIL_PROVIDER", "none").strip().lower(),
        "EMAIL_VERIFIED": env_bool("ZENDOC_EMAIL_VERIFIED", False),
        "SMTP_HOST": os.environ.get("ZENDOC_SMTP_HOST", "").strip(),
        "SMTP_PORT": env_int("ZENDOC_SMTP_PORT", 587, minimum=1, maximum=65535),
        "SMTP_USERNAME": os.environ.get("ZENDOC_SMTP_USERNAME", "").strip(),
        "SMTP_PASSWORD": os.environ.get("ZENDOC_SMTP_PASSWORD", ""),
        "SMTP_FROM_EMAIL": os.environ.get("ZENDOC_SMTP_FROM_EMAIL", "").strip(),
        "SMTP_USE_TLS": env_bool("ZENDOC_SMTP_USE_TLS", True),
        "SMTP_USE_SSL": env_bool("ZENDOC_SMTP_USE_SSL", False),
        "SMTP_TIMEOUT": env_int("ZENDOC_SMTP_TIMEOUT", 15, minimum=1, maximum=120),
        "ANDROID_PACKAGE_NAME": os.environ.get("ZENDOC_ANDROID_PACKAGE_NAME", "").strip(),
        "ANDROID_SHA256_CERT_FINGERPRINT": os.environ.get(
            "ZENDOC_ANDROID_SHA256_CERT_FINGERPRINT", ""
        ).strip(),
        "S3_ENDPOINT_URL": os.environ.get("ZENDOC_S3_ENDPOINT_URL", "").strip(),
        "S3_REGION": os.environ.get("ZENDOC_S3_REGION", "auto").strip(),
        "S3_BUCKET": os.environ.get("ZENDOC_S3_BUCKET", "").strip(),
        "S3_ACCESS_KEY_ID": os.environ.get("ZENDOC_S3_ACCESS_KEY_ID", "").strip(),
        "S3_SECRET_ACCESS_KEY": os.environ.get("ZENDOC_S3_SECRET_ACCESS_KEY", ""),
        "S3_SERVER_SIDE_ENCRYPTION": os.environ.get(
            "ZENDOC_S3_SERVER_SIDE_ENCRYPTION", "AES256"
        ).strip(),
        "SLM_ENABLED": env_bool("ZENDOC_SLM_ENABLED", False),
        "SLM_PROVIDER": os.environ.get("ZENDOC_SLM_PROVIDER", "ollama").strip().lower(),
        "SLM_BASE_URL": os.environ.get("ZENDOC_SLM_BASE_URL", "http://127.0.0.1:11434").strip(),
        "SLM_MODEL": os.environ.get("ZENDOC_SLM_MODEL", "").strip(),
        "SLM_TIMEOUT": env_int("ZENDOC_SLM_TIMEOUT", 10),
        # Milestone 8.1 canonical local-AI configuration. The older SLM names
        # remain readable during the compatibility window.
        "LOCAL_AI_ENABLED": env_bool(
            "ZENDOC_LOCAL_AI_ENABLED", env_bool("ZENDOC_SLM_ENABLED", False)
        ),
        "LOCAL_AI_PROVIDER": os.environ.get(
            "ZENDOC_LOCAL_AI_PROVIDER", os.environ.get("ZENDOC_SLM_PROVIDER", "ollama")
        ).strip().lower(),
        "LOCAL_AI_BASE_URL": os.environ.get(
            "ZENDOC_LOCAL_AI_BASE_URL",
            os.environ.get("ZENDOC_SLM_BASE_URL", "http://127.0.0.1:11434"),
        ).strip(),
        "LOCAL_AI_MODEL": os.environ.get(
            "ZENDOC_LOCAL_AI_MODEL", os.environ.get("ZENDOC_SLM_MODEL", "")
        ).strip(),
        "LOCAL_AI_TIMEOUT": env_int(
            "ZENDOC_LOCAL_AI_TIMEOUT",
            env_int("ZENDOC_SLM_TIMEOUT", 10),
        ),
        "LOCAL_AI_ALLOW_PRIVATE_NETWORK": env_bool(
            "ZENDOC_LOCAL_AI_ALLOW_PRIVATE_NETWORK", False
        ),
        "MODEL_EVALUATION_REAL_ENABLED": env_bool(
            "ZENDOC_MODEL_EVALUATION_REAL_ENABLED", False
        ),
        "AI_PROVIDER": ai_provider,
        "AI_API_KEY": os.environ.get("ZENDOC_AI_API_KEY", "").strip(),
        "AI_BASE_URL": ai_base_url,
        "AI_MODEL": os.environ.get("ZENDOC_AI_MODEL", "").strip(),
        "AI_TIMEOUT": env_int("ZENDOC_AI_TIMEOUT", 20),
        # Connected Care never silently falls back to synthetic operational
        # data. A demo run must opt in explicitly and is labelled at every UI
        # boundary; production therefore remains LIVE by default.
        "CONNECTED_CARE_DATA_MODE": connected_care_data_mode,
    }
    config.update(database_config)
    if overrides:
        config.update(overrides)
    return config


def validate_startup_config(app):
    if app.config.get("TESTING"):
        return
    if app.config["ZENDOC_ENV"] == "production":
        missing = []
        for key in ("SECRET_KEY", "ADMIN_EMAIL", "ADMIN_PASSWORD"):
            if not app.config.get(key):
                missing.append(key)
        if missing:
            raise ConfigError(f"Missing required production config: {', '.join(missing)}")
        if app.debug:
            raise ConfigError("Flask debug mode must be disabled in production.")
        if app.config.get("DATABASE_DURABILITY") == "integration_required":
            message = (
                "Production persistence is not durable: SQLite is using an unverified service-local path. "
                "Configure DATABASE_URL for PostgreSQL or an explicitly verified persistent SQLite mount."
            )
            if app.config.get("REQUIRE_DURABLE_DATABASE"):
                raise ConfigError(message)
            app.logger.critical(message)

        if app.config.get("PUBLIC_RELEASE_REQUIRED"):
            public_missing = []
            public_base_url = str(app.config.get("PUBLIC_BASE_URL") or "").strip()
            support_email = str(app.config.get("SUPPORT_EMAIL") or "").strip()
            storage_provider = str(app.config.get("STORAGE_PROVIDER") or "local").strip().lower()
            telehealth_provider = str(app.config.get("TELEHEALTH_PROVIDER") or "local_demo").strip().lower()
            connected_mode = str(app.config.get("CONNECTED_CARE_DATA_MODE") or "LIVE").strip().upper()

            if not public_base_url.lower().startswith("https://"):
                public_missing.append("HTTPS ZENDOC_PUBLIC_BASE_URL")
            if not support_email or "@" not in support_email:
                public_missing.append("ZENDOC_SUPPORT_EMAIL")
            if not bool(app.config.get("PERSISTENCE_VERIFIED")):
                public_missing.append("ZENDOC_PERSISTENCE_VERIFIED=true")
            if not bool(app.config.get("BACKUP_VERIFIED")):
                public_missing.append("ZENDOC_BACKUP_VERIFIED=true")
            if str(app.config.get("EMAIL_PROVIDER") or "").strip().lower() != "smtp":
                public_missing.append("ZENDOC_EMAIL_PROVIDER=smtp")
            if not str(app.config.get("SMTP_HOST") or "").strip():
                public_missing.append("ZENDOC_SMTP_HOST")
            if not str(app.config.get("SMTP_FROM_EMAIL") or "").strip():
                public_missing.append("ZENDOC_SMTP_FROM_EMAIL")
            if not (
                bool(app.config.get("SMTP_USE_TLS"))
                or bool(app.config.get("SMTP_USE_SSL"))
            ):
                public_missing.append("encrypted SMTP transport (TLS or SSL)")
            if not bool(app.config.get("EMAIL_VERIFIED")):
                public_missing.append("ZENDOC_EMAIL_VERIFIED=true")
            if storage_provider == "local":
                public_missing.append("durable ZENDOC_STORAGE_PROVIDER")
            if storage_provider in {"s3", "s3_compatible", "r2"}:
                if not str(app.config.get("S3_BUCKET") or "").strip():
                    public_missing.append("ZENDOC_S3_BUCKET")
                if not str(app.config.get("S3_ACCESS_KEY_ID") or "").strip():
                    public_missing.append("ZENDOC_S3_ACCESS_KEY_ID")
                if not str(app.config.get("S3_SECRET_ACCESS_KEY") or ""):
                    public_missing.append("ZENDOC_S3_SECRET_ACCESS_KEY")
                endpoint_url = str(app.config.get("S3_ENDPOINT_URL") or "").strip()
                if endpoint_url and not endpoint_url.lower().startswith("https://"):
                    public_missing.append("HTTPS ZENDOC_S3_ENDPOINT_URL")
            if not bool(app.config.get("STORAGE_VERIFIED")):
                public_missing.append("ZENDOC_STORAGE_VERIFIED=true")
            if connected_mode != "LIVE":
                public_missing.append("ZENDOC_CONNECTED_CARE_DATA_MODE=LIVE")
            if telehealth_provider == "local_demo":
                public_missing.append("non-demo ZENDOC_TELEHEALTH_PROVIDER")

            if public_missing:
                raise ConfigError(
                    "Public release startup blocked. Missing or unverified: "
                    + ", ".join(public_missing)
                )
