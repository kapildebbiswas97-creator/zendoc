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
    config = {
        "ZENDOC_ENV": env,
        "SECRET_KEY": secret_key or "development-only-secret-key",
        "UPLOAD_FOLDER": str(base_dir / "uploads"),
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
        "PLACES_PROVIDER": os.environ.get("ZENDOC_PLACES_PROVIDER", "none"),
        "VIDEO_PROVIDER": os.environ.get("ZENDOC_VIDEO_PROVIDER", "none"),
        "YOUTUBE_API_KEY": os.environ.get("ZENDOC_YOUTUBE_API_KEY", ""),
        "REQUIRE_DURABLE_DATABASE": env_bool("ZENDOC_REQUIRE_DURABLE_DATABASE", False),
        "STORAGE_PROVIDER": os.environ.get("ZENDOC_STORAGE_PROVIDER", "local").strip().lower(),
        "TELEHEALTH_PROVIDER": os.environ.get("ZENDOC_TELEHEALTH_PROVIDER", "local_demo").strip().lower(),
        "REALTIME_PROVIDER": os.environ.get("ZENDOC_REALTIME_PROVIDER", "polling").strip().lower(),
        "NOTIFICATION_PROVIDER": os.environ.get("ZENDOC_NOTIFICATION_PROVIDER", "in_app").strip().lower(),
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
