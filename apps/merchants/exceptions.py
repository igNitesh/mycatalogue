class SoleOwnerProtectionError(Exception):
    """
    Raised when an operation (demotion, suspension, revocation, or deletion)
    would leave a merchant without at least one active owner.
    """

    pass


class MerchantPermissionDeniedError(Exception):
    """Raised when an action is prohibited by the merchant authorization matrix."""

    pass
