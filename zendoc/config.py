import os


class ConfigError(RuntimeError):
    pass


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(base_dir, overrides=None):
    env = os.environ.get("ZENDOC_ENV", "development").strip().lower()
    testing = bool(overrides and overrides.get("TESTING"))
    secret_key = os.environ.get("ZENDOC_SECRET_KEY")
    if not secret_key and (env == "production" and not testing):
        raise ConfigError("ZENDOC_SECRET_KEY is required in production.")

    config = {
        "ZENDOC_ENV": env,
        "SECRET_KEY": secret_key or "development-only-secret-key",
        "DATABASE": str(base_dir / "instance" / "zendoc.db"),
        "UPLOAD_FOLDER": str(base_dir / "uploads"),
        "MAX_CONTENT_LENGTH": int(os.environ.get("ZENDOC_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": env == "production",
        "ADMIN_EMAIL": os.environ.get("ZENDOC_ADMIN_EMAIL", "bhimchandrabiswas267@gmail.com"),
        "ADMIN_PASSWORD": os.environ.get("ZENDOC_ADMIN_PASSWORD"),
        "CREATE_DEV_ADMIN": env != "production" and env_bool("ZENDOC_CREATE_DEV_ADMIN", True),
        "RATE_LIMIT_PER_MINUTE": int(os.environ.get("ZENDOC_RATE_LIMIT_PER_MINUTE", "120")),
        "PLACES_PROVIDER": os.environ.get("ZENDOC_PLACES_PROVIDER", "none"),
        "VIDEO_PROVIDER": os.environ.get("ZENDOC_VIDEO_PROVIDER", "none"),
        "YOUTUBE_API_KEY": os.environ.get("ZENDOC_YOUTUBE_API_KEY", ""),
    }
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
