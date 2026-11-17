"""
Domain exception classes for the products and categories application.
"""


class ProductError(Exception):
    """Base exception for all product and catalogue domain errors."""


class ProductNotFoundError(ProductError):
    """Raised when a requested product does not exist."""


class CategoryNotFoundError(ProductError):
    """Raised when a requested category does not exist."""


class ProductPermissionDeniedError(ProductError):
    """Raised when an actor lacks permission to perform a product or category mutation."""


class CrossTenantAssignmentError(ProductError):
    """Raised when attempting to associate a product and category belonging to different merchants."""


class ProductSlugAlreadyTakenError(ProductError):
    """Raised when a product slug is already taken within the merchant's catalogue."""


class CategorySlugAlreadyTakenError(ProductError):
    """Raised when a category slug is already taken within the merchant's catalogue."""


class DuplicateSKUError(ProductError):
    """Raised when a SKU already exists for another product belonging to the same merchant."""


class InvalidProductAttributeError(ProductError):
    """Raised when custom product attributes fail validation rules."""


class ProductLifecycleError(ProductError):
    """Raised when an invalid product lifecycle status transition is attempted."""


class InvalidProductImageError(ProductError):
    """Raised when an uploaded product image fails format, size, or decoding validation."""
