"""Error taxonomy for vision analysis.

Codes are assigned to these types by the machine-readable API layer; the
messages carried by these exceptions are safe to show to users.
"""


class VisionError(Exception):
    """Base class for vision analysis failures."""


class ProviderNotConfiguredError(VisionError):
    """The AI provider is missing configuration (e.g. no API key)."""


class InvalidImageError(VisionError):
    """The screenshot to analyze could not be read."""


class ProviderRequestError(VisionError):
    """The provider request failed (network or HTTP error)."""


class ProviderAuthError(ProviderRequestError):
    """The provider rejected the configured credentials."""


class ProviderRateLimitError(ProviderRequestError):
    """The provider rate limit was reached."""


class ProviderResponseError(VisionError):
    """The provider response could not be parsed."""


class ProviderEmptyResponseError(ProviderResponseError):
    """The provider returned an empty answer."""
