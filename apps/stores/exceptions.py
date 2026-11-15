class StoreDomainError(Exception):
    """Base domain exception for store operations."""

    pass


class SlugValidationError(StoreDomainError):
    """Raised when a slug contains invalid characters, format, or is a reserved word."""

    pass


class SlugAlreadyTakenError(StoreDomainError):
    """Raised when a store slug conflicts with an existing store."""

    pass


class DuplicateStoreError(StoreDomainError):
    """Raised when attempting to create a second store for a merchant."""

    pass


class StorePublishError(StoreDomainError):
    """Raised when publishing prerequisites are not satisfied."""

    pass


class StorePermissionDeniedError(StoreDomainError):
    """Raised when an actor lacks permission to perform a store action."""

    pass
