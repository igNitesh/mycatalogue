import os
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.functions import Lower
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.merchants.choices import MerchantStatus
from apps.merchants.mixins import MerchantContextMixin
from apps.merchants.permissions import MerchantPermission, can_perform_merchant_action
from apps.users.decorators import VerifiedUserRequiredMixin

from .exceptions import (
    DuplicateStoreError,
    SlugAlreadyTakenError,
    SlugValidationError,
    StorePermissionDeniedError,
    StorePublishError,
)
from .forms import StoreCreationForm, StoreProfileForm, StoreSlugForm
from .models import Store
from .services import (
    _UNSET,
    change_store_slug,
    create_store,
    publish_store,
    unpublish_store,
    update_store_profile,
)
from .validators import RESERVED_SLUGS, normalize_slug, validate_and_normalize_slug


def _safe_remove_file(file_path: str | None) -> None:
    """Safely delete an obsolete media file from disk after database commit."""
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


class StoreSettingsView(LoginRequiredMixin, VerifiedUserRequiredMixin, MerchantContextMixin, View):
    """
    Main store management interface for the active merchant organization.

    Behaviors:
    - If merchant has no store: renders store creation form.
    - If merchant has a store: renders store profile, slug, and publishing management.
    - Strictly authorized via MerchantPermission.MANAGE_STORE.
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not getattr(request.user, "is_verified", False):
            return redirect("users:verification_required")

        if not getattr(request, "merchant", None) or not getattr(request, "membership", None):
            messages.info(
                request,
                _("Please select an active business organization to access Store Settings."),
            )
            return redirect("merchants:dashboard")

        if not can_perform_merchant_action(request.membership, MerchantPermission.MANAGE_STORE):
            raise PermissionDenied(
                _("You lack permission to manage store settings for this business.")
            )

        return super().dispatch(request, *args, **kwargs)

    def get_store(self) -> Store | None:
        if not getattr(self, "merchant", None):
            return None
        return Store.objects.filter(merchant=self.merchant).first()

    def get(self, request: HttpRequest) -> HttpResponse:
        store = self.get_store()

        if store is None:
            form = StoreCreationForm(initial={"name": self.merchant.name})
            return render(
                request,
                "stores/management/create.html",
                {
                    "merchant": self.merchant,
                    "membership": self.membership,
                    "form": form,
                },
            )

        can_change_slug = can_perform_merchant_action(
            self.membership, MerchantPermission.CHANGE_STORE_SLUG
        )
        can_publish = can_perform_merchant_action(self.membership, MerchantPermission.PUBLISH_STORE)
        merchant_is_active = self.merchant.status == MerchantStatus.ACTIVE

        profile_form = StoreProfileForm(
            initial={
                "name": store.name,
                "description": store.description,
            }
        )
        slug_form = StoreSlugForm(initial={"slug": store.slug})

        return render(
            request,
            "stores/management/settings.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "store": store,
                "profile_form": profile_form,
                "slug_form": slug_form,
                "can_change_slug": can_change_slug,
                "can_publish": can_publish,
                "merchant_is_active": merchant_is_active,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        store = self.get_store()

        # 1. Store Creation Flow (when no store exists)
        if store is None:
            form = StoreCreationForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    create_store(
                        merchant_id=self.merchant.id,
                        actor=request.user,
                        name=form.cleaned_data["name"],
                        slug=form.cleaned_data["slug"],
                        description=form.cleaned_data.get("description", ""),
                        logo=form.cleaned_data.get("logo"),
                        cover_image=form.cleaned_data.get("cover_image"),
                    )
                    messages.success(
                        request,
                        _(
                            "Digital storefront created successfully in Draft status! "
                            "You can now manage your branding, URL, and publishing."
                        ),
                    )
                    return redirect("merchants:store_settings")
                except SlugAlreadyTakenError as exc:
                    form.add_error("slug", str(exc))
                except (DuplicateStoreError, ValidationError, StorePermissionDeniedError) as exc:
                    form.add_error(None, str(exc))

            return render(
                request,
                "stores/management/create.html",
                {
                    "merchant": self.merchant,
                    "membership": self.membership,
                    "form": form,
                },
            )

        # 2. Store Profile Update Flow (when store exists)
        profile_form = StoreProfileForm(request.POST, request.FILES)
        can_change_slug = can_perform_merchant_action(
            self.membership, MerchantPermission.CHANGE_STORE_SLUG
        )
        can_publish = can_perform_merchant_action(self.membership, MerchantPermission.PUBLISH_STORE)
        merchant_is_active = self.merchant.status == MerchantStatus.ACTIVE
        slug_form = StoreSlugForm(initial={"slug": store.slug})

        if profile_form.is_valid():
            # Track old file paths for safe post-commit cleanup
            old_logo_path = None
            old_cover_path = None
            try:
                if store.logo and os.path.isfile(store.logo.path):
                    old_logo_path = store.logo.path
            except Exception:
                pass
            try:
                if store.cover_image and os.path.isfile(store.cover_image.path):
                    old_cover_path = store.cover_image.path
            except Exception:
                pass

            # Resolve logo field update
            if profile_form.cleaned_data.get("clear_logo"):
                logo_val: Any = None
            elif profile_form.cleaned_data.get("logo"):
                logo_val = profile_form.cleaned_data["logo"]
            else:
                logo_val = _UNSET

            # Resolve cover_image field update
            if profile_form.cleaned_data.get("clear_cover_image"):
                cover_val: Any = None
            elif profile_form.cleaned_data.get("cover_image"):
                cover_val = profile_form.cleaned_data["cover_image"]
            else:
                cover_val = _UNSET

            try:
                update_store_profile(
                    store_id=store.id,
                    actor=request.user,
                    name=profile_form.cleaned_data["name"],
                    description=profile_form.cleaned_data.get("description", ""),
                    logo=logo_val,
                    cover_image=cover_val,
                )

                # Safely clean up old files after database commit succeeds
                if logo_val is not _UNSET and old_logo_path:
                    _safe_remove_file(old_logo_path)
                if cover_val is not _UNSET and old_cover_path:
                    _safe_remove_file(old_cover_path)

                messages.success(request, _("Store profile updated successfully."))
                return redirect("merchants:store_settings")
            except (ValidationError, StorePermissionDeniedError) as exc:
                profile_form.add_error(None, str(exc))

        return render(
            request,
            "stores/management/settings.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "store": store,
                "profile_form": profile_form,
                "slug_form": slug_form,
                "can_change_slug": can_change_slug,
                "can_publish": can_publish,
                "merchant_is_active": merchant_is_active,
            },
        )


class StoreSlugUpdateView(
    LoginRequiredMixin, VerifiedUserRequiredMixin, MerchantContextMixin, View
):
    """
    Dedicated POST endpoint for changing the store URL slug.
    Strictly authorized via MerchantPermission.CHANGE_STORE_SLUG.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        if not getattr(request, "merchant", None) or not getattr(request, "membership", None):
            return redirect("merchants:dashboard")

        if not can_perform_merchant_action(
            request.membership, MerchantPermission.CHANGE_STORE_SLUG
        ):
            raise PermissionDenied(_("You lack permission to change the store URL slug."))

        store = Store.objects.filter(merchant=self.merchant).first()
        if not store:
            raise Http404(_("No store found for this business organization."))

        form = StoreSlugForm(request.POST)
        if form.is_valid():
            new_slug = form.cleaned_data["slug"]
            try:
                change_store_slug(
                    store_id=store.id,
                    actor=request.user,
                    new_slug=new_slug,
                )
                messages.success(
                    request,
                    _("Store public URL slug updated successfully to '%(slug)s'.")
                    % {"slug": new_slug},
                )
                return redirect("merchants:store_settings")
            except SlugAlreadyTakenError as exc:
                form.add_error("slug", str(exc))
            except (SlugValidationError, StorePermissionDeniedError, ValidationError) as exc:
                form.add_error(None, str(exc))

        # Re-render settings page with slug form errors
        can_publish = can_perform_merchant_action(self.membership, MerchantPermission.PUBLISH_STORE)
        merchant_is_active = self.merchant.status == MerchantStatus.ACTIVE
        profile_form = StoreProfileForm(
            initial={
                "name": store.name,
                "description": store.description,
            }
        )

        return render(
            request,
            "stores/management/settings.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "store": store,
                "profile_form": profile_form,
                "slug_form": form,
                "can_change_slug": True,
                "can_publish": can_publish,
                "merchant_is_active": merchant_is_active,
            },
        )


class StoreSlugCheckView(LoginRequiredMixin, VerifiedUserRequiredMixin, MerchantContextMixin, View):
    """
    HTMX endpoint for real-time slug format and availability feedback.
    Requires CHANGE_STORE_SLUG permission and excludes current store from collisions.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        if not getattr(request, "merchant", None) or not getattr(request, "membership", None):
            return HttpResponseForbidden("Merchant context required.")

        if not can_perform_merchant_action(
            request.membership, MerchantPermission.CHANGE_STORE_SLUG
        ):
            return HttpResponseForbidden("Permission denied.")

        raw_slug = request.GET.get("slug", "").strip()
        if not raw_slug:
            return HttpResponse("")

        store = getattr(self.merchant, "store", None)
        current_store_id = store.id if store else None

        normalized = normalize_slug(raw_slug)

        # 1. Format and reserved checks
        try:
            valid_slug = validate_and_normalize_slug(normalized)
        except SlugValidationError as exc:
            return render(
                request,
                "stores/management/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "message": str(exc),
                },
            )

        # 2. Exclude current store from collision check
        qs = Store.objects.annotate(lower_slug=Lower("slug")).filter(lower_slug=valid_slug)
        if current_store_id:
            qs = qs.exclude(id=current_store_id)

        if qs.exists():
            return render(
                request,
                "stores/management/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "message": _("The slug '%(slug)s' is already in use by another store.")
                    % {"slug": valid_slug},
                },
            )

        if valid_slug in RESERVED_SLUGS:
            return render(
                request,
                "stores/management/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "message": _("The slug '%(slug)s' is reserved by the platform.")
                    % {"slug": valid_slug},
                },
            )

        # Success - available
        return render(
            request,
            "stores/management/partials/slug_feedback.html",
            {
                "is_valid": True,
                "message": _("Slug is available: /s/%(slug)s/") % {"slug": valid_slug},
            },
        )


class StorePublishToggleView(
    LoginRequiredMixin, VerifiedUserRequiredMixin, MerchantContextMixin, View
):
    """
    Dedicated POST endpoint for explicit publish/unpublish transitions.
    Strictly authorized via MerchantPermission.PUBLISH_STORE.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        if not getattr(request, "merchant", None) or not getattr(request, "membership", None):
            return redirect("merchants:dashboard")

        if not can_perform_merchant_action(request.membership, MerchantPermission.PUBLISH_STORE):
            raise PermissionDenied(_("You lack permission to change store publication state."))

        store = Store.objects.filter(merchant=self.merchant).first()
        if not store:
            raise Http404(_("No store found for this business organization."))

        action = request.POST.get("action", "").strip().lower()

        if action == "publish":
            try:
                publish_store(store_id=store.id, actor=request.user)
                messages.success(
                    request,
                    _(
                        "Store published successfully! Your digital storefront is now accessible to the public."
                    ),
                )
            except StorePublishError as exc:
                messages.error(request, str(exc))
            except (StorePermissionDeniedError, ValidationError) as exc:
                messages.error(request, str(exc))

        elif action == "unpublish":
            try:
                unpublish_store(store_id=store.id, actor=request.user)
                messages.info(
                    request,
                    _("Store unpublished. Your digital storefront is now offline to the public."),
                )
            except (StorePermissionDeniedError, ValidationError) as exc:
                messages.error(request, str(exc))

        else:
            return HttpResponseBadRequest(_("Invalid action. Must be 'publish' or 'unpublish'."))

        return redirect("merchants:store_settings")
