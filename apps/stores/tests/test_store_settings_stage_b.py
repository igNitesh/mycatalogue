import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.services import create_merchant
from apps.stores.forms import StoreProfileForm
from apps.stores.services import create_store

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="stageb.owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="stageb.other@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def merchant_alpha(db, owner_user):
    merchant, _ = create_merchant(
        owner_user=owner_user,
        name="Alpha Goods",
        business_type=BusinessType.RETAIL,
        contact_number="+91 9876543210",
        email="alpha@example.com",
        address="100 Market St",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()
    return merchant


@pytest.fixture
def store_alpha(db, merchant_alpha, owner_user):
    return create_store(
        merchant_id=merchant_alpha,
        actor=owner_user,
        name="Alpha Store",
        slug="alpha-store",
        description="Original store description.",
        tagline="Handcrafted Excellence",
        whatsapp_number="+919876543210",
        allow_whatsapp_fallback=True,
        social_links={
            "instagram": "https://instagram.com/alphagoods",
            "website": "https://alphagoods.com",
        },
    )


@pytest.mark.django_db
class TestStoreSettingsFormStageB:
    """Tests StoreProfileForm validation for Stage B evolution fields."""

    def test_form_valid_with_all_stage_b_fields(self):
        form = StoreProfileForm(
            data={
                "name": "Alpha Store Updated",
                "tagline": "Modern Artisanal Living",
                "description": "Premium apparel and lifestyle wares.",
                "whatsapp_number": "+91 98765 00000",
                "allow_whatsapp_fallback": "on",
                "social_instagram": "https://instagram.com/alpha_updated",
                "social_facebook": "https://facebook.com/alphagoods",
                "social_youtube": "https://youtube.com/@alphagoods",
                "social_twitter_x": "https://x.com/alphagoods",
                "social_pinterest": "https://pinterest.com/alphagoods",
                "social_website": "https://alpha-store.example.com",
            }
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["tagline"] == "Modern Artisanal Living"
        assert form.cleaned_data["whatsapp_number"] == "+91 98765 00000"
        assert form.cleaned_data["allow_whatsapp_fallback"] is True
        assert form.cleaned_data["social_links"] == {
            "instagram": "https://instagram.com/alpha_updated",
            "facebook": "https://facebook.com/alphagoods",
            "youtube": "https://youtube.com/@alphagoods",
            "twitter_x": "https://x.com/alphagoods",
            "pinterest": "https://pinterest.com/alphagoods",
            "website": "https://alpha-store.example.com",
        }

    def test_tagline_exceeding_120_chars_rejected(self):
        form = StoreProfileForm(
            data={
                "name": "Alpha Store",
                "tagline": "T" * 121,
            }
        )
        assert not form.is_valid()
        assert "tagline" in form.errors
        assert "120 characters" in form.errors["tagline"][0]

    def test_whatsapp_number_exceeding_20_chars_rejected(self):
        form = StoreProfileForm(
            data={
                "name": "Alpha Store",
                "whatsapp_number": "+123456789012345678901",
            }
        )
        assert not form.is_valid()
        assert "whatsapp_number" in form.errors
        assert "20 characters" in form.errors["whatsapp_number"][0]

    def test_social_link_insecure_http_rejected(self):
        form = StoreProfileForm(
            data={
                "name": "Alpha Store",
                "social_instagram": "http://instagram.com/insecure",
            }
        )
        assert not form.is_valid()
        assert "social_instagram" in form.errors
        assert "HTTPS" in form.errors["social_instagram"][0]

    def test_allow_whatsapp_fallback_unchecked_evaluates_to_false(self):
        form = StoreProfileForm(
            data={
                "name": "Alpha Store",
                # allow_whatsapp_fallback is omitted when checkbox is unchecked in browser POST
            }
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["allow_whatsapp_fallback"] is False


@pytest.mark.django_db
class TestStoreSettingsViewStageB:
    """Verifies that the StoreSettingsView properly renders and updates Stage B fields."""

    def test_get_settings_populates_initial_stage_b_fields(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 200

        content = response.content.decode()
        assert 'value="Handcrafted Excellence"' in content
        assert 'value="+919876543210"' in content
        assert 'value="https://instagram.com/alphagoods"' in content
        assert 'value="https://alphagoods.com"' in content
        assert "checked" in content  # allow_whatsapp_fallback checkbox

    def test_post_updates_stage_b_fields_and_persists_to_db(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        payload = {
            "name": "Alpha Goods Flagship",
            "description": "Redesigned flagship catalog.",
            "tagline": "Curated Essentials for Discerning Merchants",
            "whatsapp_number": "+91 99999 88888",
            "allow_whatsapp_fallback": "on",
            "social_instagram": "https://instagram.com/alpha_flagship",
            "social_website": "https://flagship.alphagoods.com",
            "social_twitter_x": "https://x.com/alpha_flagship",
        }

        response = client.post(reverse("merchants:store_settings"), data=payload)
        assert response.status_code == 302
        assert response.url == reverse("merchants:store_settings")

        store_alpha.refresh_from_db()
        assert store_alpha.name == "Alpha Goods Flagship"
        assert store_alpha.tagline == "Curated Essentials for Discerning Merchants"
        assert store_alpha.whatsapp_number == "+91 99999 88888"
        assert store_alpha.allow_whatsapp_fallback is True
        assert store_alpha.social_links == {
            "instagram": "https://instagram.com/alpha_flagship",
            "website": "https://flagship.alphagoods.com",
            "twitter_x": "https://x.com/alpha_flagship",
        }

    def test_post_unchecking_whatsapp_fallback_disables_it(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        assert store_alpha.allow_whatsapp_fallback is True

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        payload = {
            "name": store_alpha.name,
            "description": store_alpha.description,
            "tagline": store_alpha.tagline,
            "whatsapp_number": store_alpha.whatsapp_number,
            # allow_whatsapp_fallback omitted (unchecked)
        }

        response = client.post(reverse("merchants:store_settings"), data=payload)
        assert response.status_code == 302

        store_alpha.refresh_from_db()
        assert store_alpha.allow_whatsapp_fallback is False

    def test_tenant_isolation_unauthorized_user_cannot_update_store(
        self, client, other_user, merchant_alpha, store_alpha
    ):
        client.force_login(other_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_settings"),
            data={"name": "Hacked Store Name"},
        )
        assert response.status_code in (302, 403)
        store_alpha.refresh_from_db()
        assert store_alpha.name == "Alpha Store"
