class LedgerError(Exception):
    """Base error for expected command failures."""


class ConfigError(LedgerError):
    pass


class ManifestError(LedgerError):
    pass


class AuthenticationError(LedgerError):
    pass


class LarkApiError(LedgerError):
    def __init__(self, message: str, *, code: int | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class SchemaError(LedgerError):
    pass
