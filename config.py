"""Configuration for the initial local application."""

APP_NAME = "H-logsen"


class Config:
    """Keep Flask settings separate from application creation."""

    TESTING = False
    # Only these explicitly synthetic sources may be read without a real identity
    # provider. Private MySQL sources use the authenticated dataset policy.
    DEMO_READ_ENABLED = True
    PUBLIC_DEMO_SOURCES = ("demo", "empty", "partial", "unprocessed")
    BOOTSTRAP_SERVE_LOCAL = True
    MAIL_SUPPRESS_SEND = False


class DevelopmentConfig(Config):
    pass


class TestingConfig(Config):
    TESTING = True
    MAIL_SUPPRESS_SEND = True


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True


PROFILES = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
