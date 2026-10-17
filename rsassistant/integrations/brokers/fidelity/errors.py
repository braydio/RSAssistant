"""Typed Fidelity adapter failures (map 1:1 onto broker_health classes)."""


class FidelityError(Exception):
    error_class = "adapter_error"


class BrowserLaunchError(FidelityError):
    error_class = "browser_launch"


class AuthRequired(FidelityError):
    error_class = "auth"


class SessionExpired(FidelityError):
    error_class = "auth"


class SelectorChanged(FidelityError):
    error_class = "adapter_error"


class UnknownOrderOutcome(FidelityError):
    """Button clicked / request sent but no authoritative confirmation. Never retry."""

    error_class = "ambiguous_execution"
