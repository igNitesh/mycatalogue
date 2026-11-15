class SoleOwnerProtectionError(Exception):
    """
    Raised when an operation (demotion, suspension, revocation, or deletion)
    would leave a merchant without at least one active owner.
    """

    pass


class MerchantPermissionDeniedError(Exception):
    """Raised when an action is prohibited by the merchant authorization matrix."""

    pass


class NoActiveMerchantError(Exception):
    """Raised when an active merchant context is required but none is selected or available."""

    pass


class InvalidMerchantSelectionError(MerchantPermissionDeniedError):
    """Raised when an actor attempts to switch to an invalid, non-existent, or unauthorized merchant."""

    pass
