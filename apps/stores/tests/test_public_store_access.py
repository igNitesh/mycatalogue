import pytest
from django.urls import reverse

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.models import Merchant
from apps.stores.choices import StoreStatus
from apps.stores.models import Store
from apps.stores.selectors import get_public_store_by_slug


@pytest.fixture
def active_merchant(db):
    return Merchant.objects.create(
        name="Luxe Boutiques",
        email="luxe@example.com",
        contact_number="9876543210",
        address="10 Fashion Street",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.fixture
def published_store(active_merchant):
    return Store.objects.create(
        merchant=active_merchant,
        name="Luxe Official",
        slug="luxe-official",
        description="Exclusive premium fashion collection.",
        status=StoreStatus.PUBLISHED,
    )


@pytest.mark.django_db
class TestPublicStoreAccess:
    def test_selector_returns_published_store_for_active_merchant(self, published_store):
        store = get_public_store_by_slug("luxe-official")
        assert store is not None
        assert store.id == published_store.id
        assert store.name == "Luxe Official"
        assert store.merchant.name == "Luxe Boutiques"

    def test_selector_case_insensitive_and_whitespace_slug_lookup(self, published_store):
        # Uppercase
        store_upper = get_public_store_by_slug("LUXE-OFFICIAL")
        assert store_upper is not None
        assert store_upper.id == published_store.id

        # Mixed case with whitespace
        store_mixed = get_public_store_by_slug("  LuXe-OfFiCiAl  ")
        assert store_mixed is not None
        assert store_mixed.id == published_store.id

    def test_selector_returns_none_for_non_published_store(self, active_merchant):
        for non_published_status in [
            StoreStatus.DRAFT,
            StoreStatus.UNPUBLISHED,
            StoreStatus.SUSPENDED,
        ]:
            store = Store.objects.create(
                merchant=active_merchant,
                name=f"Store {non_published_status}",
                slug=f"store-{non_published_status.lower()}",
                status=non_published_status,
            )
            assert get_public_store_by_slug(store.slug) is None
            store.delete()

    def test_selector_returns_none_when_merchant_is_not_active(
        self, published_store, active_merchant
    ):
        for inactive_status in [
            MerchantStatus.PENDING,
            MerchantStatus.SUSPENDED,
            MerchantStatus.INACTIVE,
        ]:
            active_merchant.status = inactive_status
            active_merchant.save(update_fields=["status"])

            assert get_public_store_by_slug(published_store.slug) is None

    def test_selector_returns_none_for_unknown_slug(self, published_store):
        assert get_public_store_by_slug("non-existent-slug") is None
        assert get_public_store_by_slug("") is None

    def test_public_view_success_200(self, client, published_store):
        url = reverse("stores:public_detail", kwargs={"slug": published_store.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert "Luxe Official" in response.content.decode()
        assert "Exclusive premium fashion collection." in response.content.decode()
        assert "Luxe Boutiques" in response.content.decode()
        assert "9876543210" in response.content.decode()

    def test_public_view_case_insensitive_url_resolution(self, client, published_store):
        url = "/s/LUXE-OFFICIAL/"
        response = client.get(url)
        assert response.status_code == 200
        assert "Luxe Official" in response.content.decode()

    def test_public_view_404_for_draft_store(self, client, active_merchant):
        Store.objects.create(
            merchant=active_merchant,
            name="Draft Store",
            slug="draft-store",
            status=StoreStatus.DRAFT,
        )
        url = reverse("stores:public_detail", kwargs={"slug": "draft-store"})
        response = client.get(url)
        assert response.status_code == 404

    def test_public_view_404_when_merchant_is_suspended(
        self, client, published_store, active_merchant
    ):
        active_merchant.status = MerchantStatus.SUSPENDED
        active_merchant.save(update_fields=["status"])

        url = reverse("stores:public_detail", kwargs={"slug": published_store.slug})
        response = client.get(url)
        assert response.status_code == 404

    def test_public_view_404_for_nonexistent_slug(self, client):
        url = reverse("stores:public_detail", kwargs={"slug": "ghost-store"})
        response = client.get(url)
        assert response.status_code == 404

    def test_public_storefront_does_not_leak_private_merchant_or_store_data(
        self, client, published_store, active_merchant
    ):
        """
        Tenant isolation & data privacy verification:
        Ensures internal database UUIDs, exact street addresses, PIN codes,
        and internal status values are not leaked in the public storefront HTML payload.
        """
        url = reverse("stores:public_detail", kwargs={"slug": published_store.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        # Intentionally public fields MUST be present
        assert published_store.name in content
        assert published_store.slug in content
        assert active_merchant.name in content
        assert active_merchant.city in content
        assert active_merchant.state in content

        # Sensitive internal identifiers and private tenant data MUST NOT be leaked
        assert str(published_store.id) not in content
        assert str(active_merchant.id) not in content
        assert active_merchant.address not in content
        assert active_merchant.pin_code not in content
        assert active_merchant.status not in content
        assert published_store.status not in content
