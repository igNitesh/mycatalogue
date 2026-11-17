from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.merchants.mixins import MerchantContextMixin
from apps.merchants.permissions import (
    MerchantPermission,
    can_perform_merchant_action,
)
from apps.users.decorators import VerifiedUserRequiredMixin

from .choices import ProductStatus
from .exceptions import (
    CategoryNotFoundError,
    CategorySlugAlreadyTakenError,
    CrossTenantAssignmentError,
    DuplicateSKUError,
    InvalidProductImageError,
    ProductLifecycleError,
    ProductSlugAlreadyTakenError,
)
from .forms import CategoryForm, ProductForm, ProductImageUploadForm
from .models import Category, Product, ProductImage
from .selectors import (
    get_catalogue_summary,
    get_category_for_merchant,
    get_merchant_categories,
    get_merchant_products,
    get_product_for_merchant,
)
from .services import (
    _UNSET,
    add_product_image,
    archive_product,
    assign_product_categories,
    change_product_slug,
    create_category,
    create_product,
    publish_product,
    remove_product_image,
    set_primary_product_image,
    unpublish_product,
    update_category,
    update_product_profile,
)
from .validators import validate_and_normalize_slug


class MerchantCatalogueBaseView(
    LoginRequiredMixin, VerifiedUserRequiredMixin, MerchantContextMixin, View
):
    """
    Base view enforcing authentication, email verification, merchant context,
    and MANAGE_CATALOGUE permission check against merchant lifecycle.
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not getattr(request.user, "is_verified", False):
            return redirect("users:verification_required")

        if not getattr(request, "merchant", None) or not getattr(request, "membership", None):
            messages.info(
                request,
                _("Please select an active business organization to access the catalogue."),
            )
            return redirect("merchants:dashboard")

        if not can_perform_merchant_action(request.membership, MerchantPermission.MANAGE_CATALOGUE):
            raise PermissionDenied(
                _("You lack permission to manage catalogue items for this business.")
            )

        return super().dispatch(request, *args, **kwargs)


class CatalogueOverviewView(MerchantCatalogueBaseView):
    """
    Overview screen showing summary counts (total, published, draft, archived, categories),
    storefront readiness/status, and quick links.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        summary = get_catalogue_summary(self.merchant)
        recent_products = get_merchant_products(self.merchant, include_archived=False)[:5]

        store = getattr(self.merchant, "store", None)
        storefront_status = {
            "has_store": store is not None,
            "is_published": bool(store and store.status == "PUBLISHED"),
            "is_publicly_accessible": bool(store and store.is_publicly_accessible),
            "store_url": f"/s/{store.slug}/" if store else None,
            "store": store,
        }

        context = {
            "merchant": self.merchant,
            "membership": self.membership,
            "summary": summary,
            "recent_products": recent_products,
            "storefront_status": storefront_status,
            "active_nav": "products_overview",
        }
        return render(request, "products/overview.html", context)


class ProductListView(MerchantCatalogueBaseView):
    """
    Paginated, searchable, and filterable list of products for the active merchant.
    Supports HTMX partial updates for search and status/category filters.
    """

    PAGINATE_BY = 15

    def get(self, request: HttpRequest) -> HttpResponse:
        q = request.GET.get("q", "").strip()
        status = request.GET.get("status", "").strip().upper()
        category_id = request.GET.get("category", "").strip()

        selected_category = None
        if category_id:
            selected_category = get_category_for_merchant(category_id, self.merchant)

        include_archived = status == ProductStatus.ARCHIVED

        valid_status = status if status in dict(ProductStatus.choices) else None

        products_qs = get_merchant_products(
            merchant=self.merchant,
            include_archived=include_archived,
            category=selected_category,
            status=valid_status,
            search_query=q,
        )

        paginator = Paginator(products_qs, self.PAGINATE_BY)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        categories = get_merchant_categories(self.merchant, include_inactive=True)

        context = {
            "merchant": self.merchant,
            "membership": self.membership,
            "page_obj": page_obj,
            "products": page_obj.object_list,
            "categories": categories,
            "current_q": q,
            "current_status": status,
            "current_category": category_id,
            "is_filtered": bool(q or (status and status != "ACTIVE") or category_id),
            "ProductStatus": ProductStatus,
            "active_nav": "products_list",
        }

        if request.headers.get("HX-Request") == "true":
            return render(request, "products/partials/product_table.html", context)

        return render(request, "products/list.html", context)


class ProductCreateView(MerchantCatalogueBaseView):
    """
    Renders and processes the form to create a new product for the merchant.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        form = ProductForm(merchant=self.merchant)
        return render(
            request,
            "products/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "form": form,
                "is_create": True,
                "active_nav": "products_list",
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = ProductForm(request.POST, merchant=self.merchant)
        if form.is_valid():
            try:
                category_ids = [c.id for c in form.cleaned_data.get("categories", [])]
                product = create_product(
                    merchant_id=self.merchant,
                    actor=request.user,
                    name=form.cleaned_data["name"],
                    slug=form.cleaned_data.get("slug"),
                    sku=form.cleaned_data.get("sku"),
                    description=form.cleaned_data.get("description", ""),
                    price=form.cleaned_data.get("price"),
                    currency=form.cleaned_data.get("currency"),
                    category_ids=category_ids,
                    attributes=form.cleaned_data.get("attributes_json", {}),
                )
                if not form.cleaned_data.get("is_available", True):
                    update_product_profile(
                        product_id=product.id,
                        actor=request.user,
                        is_available=False,
                    )

                messages.success(
                    request,
                    _("Product '%(name)s' created successfully as draft.") % {"name": product.name},
                )
                return redirect("products:product_edit", product_id=product.id)
            except (
                ProductSlugAlreadyTakenError,
                DuplicateSKUError,
                CrossTenantAssignmentError,
                CategoryNotFoundError,
                ValidationError,
            ) as exc:
                form.add_error(None, str(exc))

        return render(
            request,
            "products/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "form": form,
                "is_create": True,
                "active_nav": "products_list",
            },
        )


class ProductEditView(MerchantCatalogueBaseView):
    """
    Renders and processes the edit form and image gallery for an existing product.
    """

    def get(self, request: HttpRequest, product_id: str) -> HttpResponse:
        product = get_product_for_merchant(product_id, self.merchant)
        if not product:
            raise Http404(_("Product not found."))

        form = ProductForm(
            merchant=self.merchant,
            product=product,
            initial={
                "name": product.name,
                "slug": product.slug,
                "sku": product.sku,
                "description": product.description,
                "price": product.price,
                "currency": product.currency,
                "is_available": product.is_available,
            },
        )
        image_form = ProductImageUploadForm()

        return render(
            request,
            "products/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "product": product,
                "form": form,
                "image_form": image_form,
                "is_create": False,
                "active_nav": "products_list",
            },
        )

    def post(self, request: HttpRequest, product_id: str) -> HttpResponse:
        product = get_product_for_merchant(product_id, self.merchant)
        if not product:
            raise Http404(_("Product not found."))

        form = ProductForm(
            request.POST,
            merchant=self.merchant,
            product=product,
        )
        image_form = ProductImageUploadForm()

        if form.is_valid():
            try:
                # 1. Update core fields
                update_product_profile(
                    product_id=product.id,
                    actor=request.user,
                    name=form.cleaned_data["name"],
                    description=form.cleaned_data.get("description", ""),
                    price=form.cleaned_data.get("price"),
                    currency=form.cleaned_data.get("currency"),
                    sku=form.cleaned_data.get("sku"),
                    is_available=form.cleaned_data.get("is_available", True),
                    attributes=form.cleaned_data.get("attributes_json", {}),
                )

                # 2. Update slug if changed
                new_slug = form.cleaned_data.get("slug")
                if new_slug and new_slug.lower() != product.slug.lower():
                    change_product_slug(
                        product_id=product.id,
                        actor=request.user,
                        new_slug=new_slug,
                    )

                # 3. Synchronize categories
                category_ids = [c.id for c in form.cleaned_data.get("categories", [])]
                assign_product_categories(
                    product_id=product.id,
                    actor=request.user,
                    category_ids=category_ids,
                )

                messages.success(request, _("Product details updated successfully."))
                return redirect("products:product_edit", product_id=product.id)
            except (
                ProductSlugAlreadyTakenError,
                DuplicateSKUError,
                CrossTenantAssignmentError,
                CategoryNotFoundError,
                ValidationError,
            ) as exc:
                form.add_error(None, str(exc))

        return render(
            request,
            "products/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "product": product,
                "form": form,
                "image_form": image_form,
                "is_create": False,
                "active_nav": "products_list",
            },
        )


class ProductPublishView(MerchantCatalogueBaseView):
    """
    POST action to publish a DRAFT product.
    """

    def post(self, request: HttpRequest, product_id: str) -> HttpResponse:
        product = get_product_for_merchant(product_id, self.merchant)
        if not product:
            raise Http404(_("Product not found."))

        try:
            publish_product(product_id=product.id, actor=request.user)
            messages.success(
                request,
                _("Product '%(name)s' is now published and visible on your catalogue.")
                % {"name": product.name},
            )
        except ProductLifecycleError as exc:
            messages.error(request, str(exc))

        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect("products:product_edit", product_id=product.id)


class ProductUnpublishView(MerchantCatalogueBaseView):
    """
    POST action to revert a PUBLISHED product to DRAFT.
    """

    def post(self, request: HttpRequest, product_id: str) -> HttpResponse:
        product = get_product_for_merchant(product_id, self.merchant)
        if not product:
            raise Http404(_("Product not found."))

        try:
            unpublish_product(product_id=product.id, actor=request.user)
            messages.info(
                request,
                _("Product '%(name)s' has been returned to draft.") % {"name": product.name},
            )
        except ProductLifecycleError as exc:
            messages.error(request, str(exc))

        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect("products:product_edit", product_id=product.id)


class ProductArchiveView(MerchantCatalogueBaseView):
    """
    POST action to archive (soft-delete) a product.
    """

    def post(self, request: HttpRequest, product_id: str) -> HttpResponse:
        product = get_product_for_merchant(product_id, self.merchant)
        if not product:
            raise Http404(_("Product not found."))

        try:
            archive_product(product_id=product.id, actor=request.user)
            messages.warning(
                request,
                _("Product '%(name)s' has been archived and removed from active catalogues.")
                % {"name": product.name},
            )
        except ProductLifecycleError as exc:
            messages.error(request, str(exc))

        return redirect("products:product_list")


class ProductImageUploadView(MerchantCatalogueBaseView):
    """
    POST action to upload and attach an image to a product gallery.
    Supports HTMX partial response rendering `products/partials/image_gallery.html`.
    """

    def post(self, request: HttpRequest, product_id: str) -> HttpResponse:
        product = get_product_for_merchant(product_id, self.merchant)
        if not product:
            raise Http404(_("Product not found."))

        form = ProductImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                add_product_image(
                    product_id=product.id,
                    actor=request.user,
                    image_file=form.cleaned_data["image"],
                    alt_text=form.cleaned_data.get("alt_text", ""),
                    is_primary=form.cleaned_data.get("is_primary", False),
                    display_order=form.cleaned_data.get("display_order") or 0,
                )
                messages.success(request, _("Image uploaded successfully."))
            except (InvalidProductImageError, ValidationError) as exc:
                form.add_error(None, str(exc))
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field}: {err}" if field != "__all__" else err)

        # Refresh product with its images
        product = get_product_for_merchant(product_id, self.merchant)

        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                "products/partials/image_gallery.html",
                {
                    "product": product,
                    "image_form": ProductImageUploadForm(),
                    "merchant": self.merchant,
                },
            )

        return redirect("products:product_edit", product_id=product_id)


class ProductImageDeleteView(MerchantCatalogueBaseView):
    """
    POST action to remove an image from a product gallery.
    Promotes next image if deleted image was primary thumbnail.
    """

    def post(self, request: HttpRequest, image_id: str) -> HttpResponse:
        image = (
            ProductImage.objects.filter(id=image_id, product__merchant=self.merchant)
            .select_related("product")
            .first()
        )
        if not image:
            raise Http404(_("Image not found."))

        product = image.product
        try:
            remove_product_image(image_id=image.id, actor=request.user)
            messages.success(request, _("Image deleted successfully."))
        except (InvalidProductImageError, ValidationError) as exc:
            messages.error(request, str(exc))

        # Refresh product
        product = get_product_for_merchant(product.id, self.merchant)

        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                "products/partials/image_gallery.html",
                {
                    "product": product,
                    "image_form": ProductImageUploadForm(),
                    "merchant": self.merchant,
                },
            )

        return redirect("products:product_edit", product_id=product.id)


class ProductImageSetPrimaryView(MerchantCatalogueBaseView):
    """
    POST action to set an image as primary thumbnail for the product.
    """

    def post(self, request: HttpRequest, image_id: str) -> HttpResponse:
        image = (
            ProductImage.objects.filter(id=image_id, product__merchant=self.merchant)
            .select_related("product")
            .first()
        )
        if not image:
            raise Http404(_("Image not found."))

        product = image.product
        try:
            set_primary_product_image(image_id=image.id, actor=request.user)
            messages.success(request, _("Primary thumbnail updated."))
        except (InvalidProductImageError, ValidationError) as exc:
            messages.error(request, str(exc))

        # Refresh product
        product = get_product_for_merchant(product.id, self.merchant)

        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                "products/partials/image_gallery.html",
                {
                    "product": product,
                    "image_form": ProductImageUploadForm(),
                    "merchant": self.merchant,
                },
            )

        return redirect("products:product_edit", product_id=product.id)


class CategoryListView(MerchantCatalogueBaseView):
    """
    Listing of all categories belonging to the merchant, including product counts and active status.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        categories = (
            get_merchant_categories(self.merchant, include_inactive=True)
            .annotate(
                product_count=Count(
                    "products",
                    filter=~Q(products__status=ProductStatus.ARCHIVED),
                )
            )
            .order_by("display_order", "name")
        )

        context = {
            "merchant": self.merchant,
            "membership": self.membership,
            "categories": categories,
            "active_nav": "categories_list",
        }
        return render(request, "products/categories/list.html", context)


class CategoryCreateView(MerchantCatalogueBaseView):
    """
    Renders and processes category creation.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        form = CategoryForm(merchant=self.merchant)
        return render(
            request,
            "products/categories/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "form": form,
                "is_create": True,
                "active_nav": "categories_list",
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = CategoryForm(request.POST, request.FILES, merchant=self.merchant)
        if form.is_valid():
            try:
                category = create_category(
                    merchant_id=self.merchant,
                    actor=request.user,
                    name=form.cleaned_data["name"],
                    slug=form.cleaned_data.get("slug"),
                    description=form.cleaned_data.get("description", ""),
                    image=form.cleaned_data.get("image"),
                    display_order=form.cleaned_data.get("display_order", 0) or 0,
                    is_active=form.cleaned_data.get("is_active", True),
                )
                messages.success(
                    request,
                    _("Category '%(name)s' created successfully.") % {"name": category.name},
                )
                return redirect("products:category_list")
            except (
                CategorySlugAlreadyTakenError,
                InvalidProductImageError,
                ValidationError,
            ) as exc:
                form.add_error(None, str(exc))

        return render(
            request,
            "products/categories/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "form": form,
                "is_create": True,
                "active_nav": "categories_list",
            },
        )


class CategoryEditView(MerchantCatalogueBaseView):
    """
    Renders and processes category editing.
    """

    def get(self, request: HttpRequest, category_id: str) -> HttpResponse:
        category = get_category_for_merchant(category_id, self.merchant)
        if not category:
            raise Http404(_("Category not found."))

        form = CategoryForm(
            merchant=self.merchant,
            category=category,
            initial={
                "name": category.name,
                "slug": category.slug,
                "description": category.description,
                "display_order": category.display_order,
                "is_active": category.is_active,
            },
        )

        return render(
            request,
            "products/categories/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "category": category,
                "form": form,
                "is_create": False,
                "active_nav": "categories_list",
            },
        )

    def post(self, request: HttpRequest, category_id: str) -> HttpResponse:
        category = get_category_for_merchant(category_id, self.merchant)
        if not category:
            raise Http404(_("Category not found."))

        form = CategoryForm(
            request.POST,
            request.FILES,
            merchant=self.merchant,
            category=category,
        )

        if form.is_valid():
            try:
                # Handle image clearing or updating
                if form.cleaned_data.get("clear_image"):
                    new_image = None
                elif request.FILES.get("image"):
                    new_image = form.cleaned_data["image"]
                else:
                    new_image = _UNSET

                update_category(
                    category_id=category.id,
                    actor=request.user,
                    name=form.cleaned_data["name"],
                    description=form.cleaned_data.get("description", ""),
                    image=new_image,
                    display_order=form.cleaned_data.get("display_order", 0) or 0,
                    is_active=form.cleaned_data.get("is_active", True),
                )
                messages.success(request, _("Category updated successfully."))
                return redirect("products:category_list")
            except (
                CategorySlugAlreadyTakenError,
                InvalidProductImageError,
                ValidationError,
            ) as exc:
                form.add_error(None, str(exc))

        return render(
            request,
            "products/categories/form.html",
            {
                "merchant": self.merchant,
                "membership": self.membership,
                "category": category,
                "form": form,
                "is_create": False,
                "active_nav": "categories_list",
            },
        )


class CategoryToggleActiveView(MerchantCatalogueBaseView):
    """
    POST action to toggle category active status.
    """

    def post(self, request: HttpRequest, category_id: str) -> HttpResponse:
        category = get_category_for_merchant(category_id, self.merchant)
        if not category:
            raise Http404(_("Category not found."))

        new_status = not category.is_active
        update_category(
            category_id=category.id,
            actor=request.user,
            is_active=new_status,
        )
        msg = (
            _("Category '%(name)s' is now active.")
            if new_status
            else _("Category '%(name)s' is now deactivated.")
        ) % {"name": category.name}
        messages.success(request, msg)

        return redirect("products:category_list")


class ProductSlugCheckView(MerchantCatalogueBaseView):
    """
    GET endpoint for real-time slug format validation and merchant-scoped uniqueness check.
    Returns partial HTML badge with feedback.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        slug = request.GET.get("slug", "").strip()
        product_id = request.GET.get("product_id", "").strip()

        if not slug:
            return HttpResponse("")

        try:
            normalized = validate_and_normalize_slug(slug, max_length=255)
        except ValidationError as exc:
            return render(
                request,
                "products/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "normalized_slug": slug,
                    "message": exc.messages[0] if exc.messages else str(exc),
                },
            )

        # Check collision within merchant
        qs = Product.objects.annotate(lower_slug=Lower("slug")).filter(
            merchant=self.merchant, lower_slug=normalized.lower()
        )
        if product_id:
            qs = qs.exclude(id=product_id)

        if qs.exists():
            return render(
                request,
                "products/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "normalized_slug": normalized,
                    "message": _("This slug is already used by another product in your catalogue."),
                },
            )

        return render(
            request,
            "products/partials/slug_feedback.html",
            {
                "is_valid": True,
                "normalized_slug": normalized,
                "message": _("Slug is available!"),
            },
        )


class CategorySlugCheckView(MerchantCatalogueBaseView):
    """
    GET endpoint for category slug availability check.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        slug = request.GET.get("slug", "").strip()
        category_id = request.GET.get("category_id", "").strip()

        if not slug:
            return HttpResponse("")

        try:
            normalized = validate_and_normalize_slug(slug, max_length=160)
        except ValidationError as exc:
            return render(
                request,
                "products/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "normalized_slug": slug,
                    "message": exc.messages[0] if exc.messages else str(exc),
                },
            )

        qs = Category.objects.annotate(lower_slug=Lower("slug")).filter(
            merchant=self.merchant, lower_slug=normalized.lower()
        )
        if category_id:
            qs = qs.exclude(id=category_id)

        if qs.exists():
            return render(
                request,
                "products/partials/slug_feedback.html",
                {
                    "is_valid": False,
                    "normalized_slug": normalized,
                    "message": _(
                        "This slug is already used by another category in your catalogue."
                    ),
                },
            )

        return render(
            request,
            "products/partials/slug_feedback.html",
            {
                "is_valid": True,
                "normalized_slug": normalized,
                "message": _("Slug is available!"),
            },
        )
