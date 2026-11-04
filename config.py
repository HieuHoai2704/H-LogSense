"""Configuration for the initial local application."""


class Config:
    """Keep Flask settings separate from application creation."""

    TESTING = False
    # Only these explicitly synthetic sources may be read without a real identity
    # provider. Private MySQL sources use the authenticated dataset policy.
    DEMO_READ_ENABLED = True
    PUBLIC_DEMO_SOURCES = ('demo', 'empty', 'partial', 'unprocessed')
