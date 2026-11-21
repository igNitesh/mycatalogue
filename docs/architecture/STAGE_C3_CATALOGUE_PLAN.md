# Stage C3 Implementation Plan — Public Product Catalogue & Search Pipeline (Revision 2)

**Document:** `docs/architecture/STAGE_C3_CATALOGUE_PLAN.md`  
**Stage:** C3 — Public Product Listing & Search Pipeline (`/s/<store-slug>/products/`)  
**Status:** PROPOSED & PENDING HUMAN APPROVAL  
**Branch:** `master`  
**Repository:** `igNitesh/mycatalogue`  
**Stitch Screens Reference:**  
- Screen 4: *Mobile Products Listing — Myntra Style* (ID: `a8715da9fbd24490adacb03a3edccdb2`, 780 × 2808 px)  
- Screen 5: *All Products Listing — Krishna Garments* (ID: `117d821b1fc347fbbea5873a702aef80`, 2560 × 5310 px)  

---

## 1. Executive Summary & Review Corrections Implemented

This revised Stage C3 implementation plan addresses all feedback from the initial architecture submission:

1. **Product Detail Links Deferred to Stage C4:**
   - No product detail links (`/s/<store-slug>/products/<product-slug>/`) or `href="#"` placeholders are rendered on product cards or headings.
   - The product card component is an unlinked display card in Stage C3. Product detail navigation is strictly deferred until Stage C4 implementation.
2. **Dependency-Free Mobile Filter Interface:**
   - The mobile filter experience uses native HTML5 `<details>` / `<summary>` disclosure widgets and standard GET forms styled with Tailwind CSS.
   - Zero new JavaScript libraries, npm packages, or external dependencies are introduced. Full progressive enhancement is guaranteed.
3. **Comprehensive Query Parameter Preservation:**
   - Active parameters across `q` (search), `category` (slug), `availability` (mode), `sort` (ordering), and `page` are systematically preserved across all interface controls and pagination links.
   - Changing filters, search query, or sorting safely resets `page` to 1 while retaining all other active criteria.
4. **Deterministic Invalid-Filter Behavior & Tests:**
   - Malformed, cross-tenant, or non-existent category slugs return HTTP 200 with the empty filter results state and a "Clear filters" action.
   - Invalid availability values or unsupported sort keys gracefully fall back to defaults without throwing exceptions or 400/500 errors.
   - Invalid or out-of-range pagination parameters safely fall back to Page 1 or the last page.
5. **Robust Image Fallback & N+1 Prevention:**
   - Prefetch query orders gallery images by `-is_primary`, `display_order`, `created_at`.
   - If an image with `is_primary=True` exists, it is selected first. If no image is marked primary, the first uploaded gallery image is used as fallback. If no images exist, a styled, accessible placeholder icon is displayed.
   - Database queries remain constant regardless of the number of products displayed (0 N+1 queries).
6. **Hardened `CONTACT_FOR_PRICE` Privacy at Template & Serialization Boundaries:**
   - Numerical prices are suppressed at the template boundary (`_product_card.html`), model property boundary (`discount_percentage` returns `None`), and view context boundary (no raw numeric price exposed in public context).
   - Integration tests utilize a unique sentinel price (e.g. `Decimal("133742.00")` and MRP `Decimal("199999.00")`).
   - Asserts that sentinel numerical values never appear anywhere in rendered HTML, DOM attributes (`data-*`, `value`), script tags, or JSON payloads.
   - Proves mathematically that `CONTACT_FOR_PRICE` items sort strictly at the end (`NULLS LAST`) in both ascending and descending price sorts.
7. **Verified Existing Selector Callers:**
   - Complete audit of all repository callers of `get_public_storefront_products()` confirmed.
   - Positional `merchant: Merchant` parameter is preserved as the first argument, guaranteeing 100% backward compatibility.
8. **Robust N+1 Query-Count Prevention & Discount Edge Cases:**
   - Employs a differential query test ($Q_{12} == Q_1$) ensuring query count remains $O(1)$ constant regardless of page item count, while being robust against legitimate framework/middleware query variations (generous ceiling $\le 10$ queries).
   - Comprehensive test cases covering discount rounding edge cases (commercial half-up rounding, `<1%` suppression, equal MRP/price, and unpriced items).

---

## 2. Architecture & Backend Capabilities

### 2.1 Model Fields Verified (Zero Schema Changes or Migrations)

| Domain Model | Code Location | Verified Fields Used | Data Safety & Privacy Rules |
| :--- | :--- | :--- | :--- |
| **`Store`** | `apps/stores/models.py:14-119` | `name`, `slug`, `tagline`, `logo`, `status`, `merchant` | Public access permitted ONLY if `status == PUBLISHED` and `is_publicly_accessible == True`. |
| **`Merchant`** | `apps/merchants/models.py:10-40` | `name`, `city`, `state`, `contact_number`, `status` | Public access permitted ONLY if `status == ACTIVE`. Private attributes strictly withheld. |
| **`Category`** | `apps/products/models.py:23-90` | `name`, `slug`, `image`, `display_order`, `is_active` | Scoped strictly to `merchant=store.merchant` and `is_active=True`. |
| **`Product`** | `apps/products/models.py:91-516` | `name`, `slug`, `sku`, `price`, `mrp`, `price_display_mode`, `availability_mode`, `discount_percentage`, `status` | Filtered strictly by `merchant=store.merchant` and `status=PUBLISHED`. |
| **`ProductImage`** | `apps/products/models.py:554-585` | `image`, `is_primary`, `display_order`, `created_at` | Prefetched with fallback ordering: `-is_primary`, `display_order`, `created_at`. |

---

## 3. Selector Specification (`apps/products/selectors.py`)

### 3.1 Caller Verification Audit

An exhaustive grep across the codebase verified all existing callers of `get_public_storefront_products`:

1. [`apps/stores/views.py:26`](file:///c:/Users/nites/Desktop/mycatalogue/apps/stores/views.py#L26): passes `merchant=store.merchant, ordering="-created_at"`
2. [`apps/products/tests/test_public_visibility.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/products/tests/test_public_visibility.py): lines 37, 55, 72, 90, 95, 100, 115, 120, 163, 171 pass `merchant=merchant`
3. [`apps/stores/tests/test_storefront_homepage_c2.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/stores/tests/test_storefront_homepage_c2.py): lines 169, 174, 180, 183 pass `merchant=merchant_alpha` and ordering

**Conclusion:** The selector MUST retain `merchant: Merchant` as its primary positional argument. All new filters are keyword-only.

### 3.2 Enhanced Selector Implementation Contract

```python
ALLOWED_PUBLIC_PRODUCT_ORDERING = {
    "name": ("name",),
    "name_asc": ("name",),
    "newest": ("-created_at",),
    "-created_at": ("-created_at",),
    "price_asc": ("effective_public_price", "-created_at"),
    "price_desc": ("-effective_public_price", "-created_at"),
}


def get_public_storefront_products(
    merchant: Merchant,
    *,
    category_slug: str | None = None,
    search_query: str | None = None,
    availability_mode: str | None = None,
    ordering: str = "newest",
) -> QuerySet[Product]:
    """
    Returns published products for customer-facing digital storefront browsing.

    Hierarchical Public Visibility Invariant:
    1. Merchant status must be strictly ACTIVE.
    2. Store must exist, be in PUBLISHED status, and be publicly accessible.
    3. Product status must be strictly PUBLISHED.
    4. Availability mode OUT_OF_STOCK displays with badge (does not hide product).
    5. Contact-for-price privacy: SQL Case/When nulls price in order_by expressions.
    6. Image fallback: Prefetches gallery ordered by -is_primary, display_order, created_at.
    """
    if ordering not in ALLOWED_PUBLIC_PRODUCT_ORDERING:
        allowed = ", ".join(sorted(ALLOWED_PUBLIC_PRODUCT_ORDERING.keys()))
        raise ValueError(f"Invalid ordering '{ordering}'. Allowed choices: {allowed}")

    if not merchant or merchant.status != MerchantStatus.ACTIVE:
        return Product.objects.none()

    store = getattr(merchant, "store", None)
    if not store or store.status != StoreStatus.PUBLISHED or not store.is_publicly_accessible:
        return Product.objects.none()

    # SQL Case/When nulling for privacy-safe price sorting
    effective_price_expr = Case(
        When(
            price_display_mode=PriceDisplayMode.CONTACT_FOR_PRICE,
            then=Value(None),
        ),
        default=F("price"),
        output_field=DecimalField(max_digits=12, decimal_places=2, null=True),
    )

    qs = (
        Product.objects.filter(
            merchant=merchant,
            status=ProductStatus.PUBLISHED,
        )
        .annotate(effective_public_price=effective_price_expr)
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by("-is_primary", "display_order", "created_at"),
                to_attr="prefetched_images",
            ),
            Prefetch(
                "categories",
                queryset=Category.objects.filter(is_active=True),
            ),
        )
    )

    # 1. Search Query Filter (name and SKU)
    if search_query:
        clean_q = search_query.strip()[:100]
        if clean_q:
            qs = qs.filter(Q(name__icontains=clean_q) | Q(sku__icontains=clean_q))

    # 2. Category Filter (Case-insensitive, merchant-scoped, active-only)
    if category_slug:
        clean_cat = category_slug.strip().lower()
        category = Category.objects.filter(
            merchant=merchant,
            slug=clean_cat,
            is_active=True,
        ).first()
        if not category:
            return Product.objects.none()
        qs = qs.filter(categories=category)

    # 3. Availability Filter
    if availability_mode:
        clean_avail = availability_mode.strip().upper()
        if clean_avail in AvailabilityMode.values:
            qs = qs.filter(availability_mode=clean_avail)

    # 4. Ordering with NULLS LAST
    if ordering == "price_asc":
        qs = qs.order_by(F("effective_public_price").asc(nulls_last=True), "-created_at")
    elif ordering == "price_desc":
        qs = qs.order_by(F("effective_public_price").desc(nulls_last=True), "-created_at")
    else:
        order_fields = ALLOWED_PUBLIC_PRODUCT_ORDERING[ordering]
        qs = qs.order_by(*order_fields)

    return qs
```

---

## 4. Public View Specification (`apps/stores/views.py`)

### 4.1 Route Definition (`apps/stores/urls.py`)

```python
path("<slug:slug>/products/", views.public_product_list, name="public_products"),
```

### 4.2 View Implementation Contract

```python
def public_product_list(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Public customer-facing product catalogue listing and search view.
    Handles search (q), category, availability, sorting, pagination,
    and active parameter preservation.
    """
    store = get_public_store_by_slug(slug)
    if not store:
        raise Http404("Store not found or is not currently active.")

    merchant = store.merchant
    all_categories = get_merchant_categories(merchant)

    # 1. Extract and sanitize inputs
    raw_q = request.GET.get("q", "").strip()[:100]
    search_query = raw_q if raw_q else None

    raw_cat = request.GET.get("category", "").strip().lower()
    category_slug = raw_cat if raw_cat else None

    raw_avail = request.GET.get("availability", "").strip().upper()
    availability_mode = raw_avail if raw_avail in AvailabilityMode.values else None

    raw_sort = request.GET.get("sort", "").strip().lower()
    valid_sorts = {"newest", "price_asc", "price_desc"}
    ordering = raw_sort if raw_sort in valid_sorts else "newest"

    # 2. Selected category resolution
    selected_category = None
    if category_slug:
        selected_category = all_categories.filter(slug=category_slug).first()

    # 3. Query execution
    products_qs = get_public_storefront_products(
        merchant=merchant,
        category_slug=category_slug,
        search_query=search_query,
        availability_mode=availability_mode,
        ordering=ordering,
    )

    total_published_count = Product.objects.filter(
        merchant=merchant,
        status=ProductStatus.PUBLISHED,
    ).count()

    # 4. Pagination (12 items per page)
    paginator = Paginator(products_qs, 12)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # 5. Query preservation builders
    query_params = request.GET.copy()
    query_params.pop("page", None)
    base_query_string = query_params.urlencode()

    context = {
        "store": store,
        "categories": all_categories,
        "page_obj": page_obj,
        "paginator": paginator,
        "total_published_count": total_published_count,
        "search_query": search_query or "",
        "selected_category": selected_category,
        "selected_category_slug": category_slug or "",
        "selected_availability": availability_mode or "",
        "selected_sort": ordering,
        "base_query_string": base_query_string,
        "has_active_filters": bool(search_query or category_slug or availability_mode or (ordering != "newest")),
    }
    return render(request, "storefront/product_list.html", context)
```

---

## 5. Parameter Fallback & Error-Handling Contract

| Parameter | Type / Format | Valid Values | Invalid / Tampered Input | Deterministic System Response |
| :--- | :--- | :--- | :--- | :--- |
| **`q`** | Text string | Any non-empty string | Whitespace-only, empty, or $>100$ chars | Stripped; truncated to 100 chars. If empty, filter omitted. HTTP 200. |
| **`category`** | Slug string | Active category belonging to merchant | Cross-tenant slug, non-existent slug, or inactive | Selector returns `Product.objects.none()`. View displays HTTP 200 no-results state with "Clear all filters" CTA. |
| **`availability`** | Choice string | `in_stock`, `made_to_order`, `out_of_stock` (case-insensitive) | `discontinued`, `foo`, `123` | Silently ignored (displays all availability modes). HTTP 200. |
| **`sort`** | Enum string | `newest`, `price_asc`, `price_desc` | `rating`, `popularity`, SQL injection | View falls back to `"newest"` (`-created_at`). HTTP 200. |
| **`page`** | Integer string | `1` to `paginator.num_pages` | `abc`, `1.5`, `-5`, `99999` | Non-integers $\rightarrow$ Page 1. Out-of-bounds $\rightarrow$ Last page (or Page 1). HTTP 200. |

---

## 6. Frontend Interface & Component Specification

### 6.1 Reusable Product Card Component (`templates/storefront/partials/_product_card.html`)

**Critical Constraint:** In accordance with user instruction #1, product detail navigation is strictly deferred to Stage C4. No `<a>` tags with `/products/<slug>/` or `href="#"` placeholders are rendered.

```html
<article class="group bg-surface-container-lowest rounded-2xl border border-outline-variant/30 overflow-hidden transition-all shadow-xs hover:shadow-md flex flex-col justify-between" data-product-id="{{ product.id }}">
    <!-- 3:4 Portrait Image Container with Robust Fallbacks -->
    <div class="aspect-[3/4] w-full bg-surface-container-low overflow-hidden relative">
        {% if product.prefetched_images %}
            <img src="{{ product.prefetched_images.0.image.url }}" alt="{{ product.name }}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">
        {% elif product.primary_image %}
            <img src="{{ product.primary_image.image.url }}" alt="{{ product.name }}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">
        {% else %}
            <!-- Accessible Neutral Fallback Placeholder -->
            <div class="w-full h-full flex flex-col items-center justify-center text-outline/40 bg-surface-container-low">
                <span class="material-symbols-outlined text-4xl" aria-hidden="true">inventory_2</span>
                <span class="text-[10px] text-outline font-medium mt-1">No Image Available</span>
            </div>
        {% endif %}

        <!-- Availability Badge -->
        <div class="absolute top-2.5 left-2.5">
            {% if product.availability_mode == "IN_STOCK" %}
                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container-lowest/90 text-tertiary font-badge text-[10px] sm:text-[11px] font-bold shadow-xs backdrop-blur-sm border border-tertiary/20">
                    <span class="w-1.5 h-1.5 rounded-full bg-tertiary"></span>
                    <span>In Stock</span>
                </span>
            {% elif product.availability_mode == "MADE_TO_ORDER" %}
                <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50/95 text-amber-800 font-badge text-[10px] sm:text-[11px] font-bold shadow-xs backdrop-blur-sm border border-amber-200">
                    <span class="material-symbols-outlined text-[13px]" aria-hidden="true">handyman</span>
                    <span>Made to Order</span>
                </span>
            {% elif product.availability_mode == "OUT_OF_STOCK" %}
                <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100/95 text-slate-700 font-badge text-[10px] sm:text-[11px] font-bold shadow-xs backdrop-blur-sm border border-slate-300">
                    <span>Out of Stock</span>
                </span>
            {% endif %}
        </div>

        <!-- Commercial Discount Badge (Zero Leakage for CONTACT_FOR_PRICE) -->
        {% if product.price_display_mode != "CONTACT_FOR_PRICE" and product.discount_percentage %}
            <div class="absolute top-2.5 right-2.5">
                <span class="px-2 py-0.5 rounded-md bg-amber-100 text-amber-900 font-badge text-[10px] sm:text-[11px] font-bold shadow-xs border border-amber-300">
                    {{ product.discount_percentage }}% OFF
                </span>
            </div>
        {% endif %}
    </div>

    <!-- Product Metadata Block (Unlinked Headings - C4 Navigation Deferred) -->
    <div class="p-3 sm:p-4 flex flex-col flex-1 justify-between gap-2.5">
        <div>
            {% with cat=product.categories.all|first %}
                {% if cat %}
                    <span class="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-secondary block mb-0.5 truncate">
                        {{ cat.name }}
                    </span>
                {% endif %}
            {% endwith %}

            <h3 class="font-headline font-bold text-xs sm:text-sm text-on-surface truncate" title="{{ product.name }}">
                {{ product.name }}
            </h3>

            {% if product.sku %}
                <p class="text-[10px] font-mono text-outline mt-0.5 truncate">SKU: {{ product.sku }}</p>
            {% endif %}
        </div>

        <!-- Pricing Block (Strict Privacy Enforcement) -->
        <div class="pt-2 border-t border-outline-variant/15 flex items-baseline justify-between gap-1 flex-wrap">
            {% if product.price_display_mode == "CONTACT_FOR_PRICE" or not product.price %}
                <span class="font-headline font-bold text-xs sm:text-sm text-primary">Contact for Price</span>
            {% else %}
                <div class="flex items-baseline gap-1.5 flex-wrap">
                    <span class="font-price font-bold text-sm sm:text-base text-on-surface">
                        ₹{{ product.price|floatformat:0 }}
                    </span>
                    {% if product.mrp and product.mrp > product.price %}
                        <span class="font-price text-xs text-outline line-through">
                            ₹{{ product.mrp|floatformat:0 }}
                        </span>
                    {% endif %}
                </div>
            {% endif %}
        </div>
    </div>
    <!-- Note: Product detail navigation is deferred to Stage C4 -->
</article>
```

### 6.2 Dependency-Free Mobile Filter & Controls Interface

In accordance with user instruction #2, the mobile filter uses native HTML5 `<details>` / `<summary>` and standard HTML GET form controls:

```html
<!-- Mobile Filter Bar & Native Disclosure Drawer -->
<div class="lg:hidden mb-4">
    <details class="group bg-surface-container-lowest rounded-2xl border border-outline-variant/30 overflow-hidden shadow-xs">
        <summary class="flex items-center justify-between p-3.5 cursor-pointer list-none select-none hover:bg-surface-container-low transition-colors">
            <div class="flex items-center gap-2 text-xs sm:text-sm font-bold text-on-surface">
                <span class="material-symbols-outlined text-[20px] text-primary" aria-hidden="true">tune</span>
                <span>Filters &amp; Sorting</span>
                {% if has_active_filters %}
                    <span class="w-2 h-2 rounded-full bg-primary" aria-hidden="true"></span>
                {% endif %}
            </div>
            <div class="flex items-center gap-1 text-xs text-secondary">
                <span class group-open:hidden>Show</span>
                <span class="hidden group-open:inline">Hide</span>
                <span class="material-symbols-outlined text-[18px] group-open:rotate-180 transition-transform" aria-hidden="true">expand_more</span>
            </div>
        </summary>

        <form method="get" action="" class="p-4 border-t border-outline-variant/20 space-y-4 bg-surface-container-low/30">
            {% if search_query %}
                <input type="hidden" name="q" value="{{ search_query }}">
            {% endif %}

            <!-- Sort By -->
            <div>
                <label for="mobile-sort" class="block text-xs font-semibold text-on-surface mb-1.5">Sort Catalogue</label>
                <select id="mobile-sort" name="sort" class="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-xl px-3 py-2 text-xs text-on-surface focus:outline-none focus:border-primary">
                    <option value="newest" {% if selected_sort == "newest" %}selected{% endif %}>Newest First</option>
                    <option value="price_asc" {% if selected_sort == "price_asc" %}selected{% endif %}>Price: Low to High</option>
                    <option value="price_desc" {% if selected_sort == "price_desc" %}selected{% endif %}>Price: High to Low</option>
                </select>
            </div>

            <!-- Availability -->
            <div>
                <span class="block text-xs font-semibold text-on-surface mb-1.5">Availability</span>
                <div class="grid grid-cols-2 gap-2">
                    <label class="flex items-center gap-2 p-2 rounded-xl bg-surface-container-lowest border border-outline-variant/30 text-xs cursor-pointer">
                        <input type="radio" name="availability" value="" {% if not selected_availability %}checked{% endif %} class="text-primary focus:ring-primary">
                        <span>All Items</span>
                    </label>
                    <label class="flex items-center gap-2 p-2 rounded-xl bg-surface-container-lowest border border-outline-variant/30 text-xs cursor-pointer">
                        <input type="radio" name="availability" value="in_stock" {% if selected_availability == "IN_STOCK" %}checked{% endif %} class="text-primary focus:ring-primary">
                        <span>In Stock</span>
                    </label>
                    <label class="flex items-center gap-2 p-2 rounded-xl bg-surface-container-lowest border border-outline-variant/30 text-xs cursor-pointer">
                        <input type="radio" name="availability" value="made_to_order" {% if selected_availability == "MADE_TO_ORDER" %}checked{% endif %} class="text-primary focus:ring-primary">
                        <span>Made to Order</span>
                    </label>
                    <label class="flex items-center gap-2 p-2 rounded-xl bg-surface-container-lowest border border-outline-variant/30 text-xs cursor-pointer">
                        <input type="radio" name="availability" value="out_of_stock" {% if selected_availability == "OUT_OF_STOCK" %}checked{% endif %} class="text-primary focus:ring-primary">
                        <span>Out of Stock</span>
                    </label>
                </div>
            </div>

            <!-- Category (preserved as select on mobile) -->
            <div>
                <label for="mobile-category" class="block text-xs font-semibold text-on-surface mb-1.5">Category</label>
                <select id="mobile-category" name="category" class="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-xl px-3 py-2 text-xs text-on-surface focus:outline-none focus:border-primary">
                    <option value="" {% if not selected_category_slug %}selected{% endif %}>All Categories</option>
                    {% for cat in categories %}
                        <option value="{{ cat.slug }}" {% if selected_category_slug == cat.slug %}selected{% endif %}>{{ cat.name }}</option>
                    {% endfor %}
                </select>
            </div>

            <!-- Filter Action Buttons -->
            <div class="flex items-center gap-2 pt-2">
                <button type="submit" class="flex-1 py-2.5 px-4 bg-primary text-on-primary font-headline font-bold text-xs rounded-xl shadow-xs transition-colors hover:bg-primary-container">
                    Apply Filters
                </button>
                {% if has_active_filters %}
                    <a href="{% url 'stores:public_products' slug=store.slug %}" class="py-2.5 px-4 bg-surface-container text-on-surface font-semibold text-xs rounded-xl transition-colors hover:bg-surface-container-high text-center">
                        Reset
                    </a>
                {% endif %}
            </div>
        </form>
    </details>
</div>
```

---

## 7. Quality Gates & Automated Verification Plan

### 7.1 Automated Integration Test Suite (`apps/stores/tests/test_storefront_listing_c3.py`)

A comprehensive pytest suite covering all 8 review criteria:

```python
import pytest
from decimal import Decimal
from django.urls import reverse
from apps.products.choices import AvailabilityMode, PriceDisplayMode, ProductStatus
from apps.products.models import Category, Product, ProductImage
from apps.stores.choices import StoreStatus

@pytest.mark.django_db
class TestStorefrontListingC3:
    # 1. Tenant Isolation & Access Control
    def test_public_listing_strict_tenant_isolation(self, client, store_alpha, merchant_alpha, store_beta, merchant_beta):
        """Asserts Beta's published products never appear in Alpha's catalogue."""
        ...
    def test_public_listing_unpublished_store_404(self, client, store_alpha):
        ...
    def test_public_listing_inactive_merchant_404(self, client, store_alpha, merchant_alpha):
        ...

    # 2. Search Accuracy
    def test_public_listing_search_by_name(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_search_by_sku(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_search_whitespace_and_length_truncation(self, client, store_alpha):
        ...

    # 3. Category & Availability Filters with Invalid Fallback
    def test_public_listing_filter_by_valid_category(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_invalid_category_returns_no_results_state(self, client, store_alpha):
        """Cross-tenant or bogus category slug renders HTTP 200 with no-results state and clear CTA."""
        ...
    def test_public_listing_filter_by_availability(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_invalid_availability_falls_back_to_all(self, client, store_alpha, merchant_alpha):
        """Unrecognized availability parameter displays full catalogue without raising error."""
        ...

    # 4. Sorting & CONTACT_FOR_PRICE Hardened Privacy
    def test_public_listing_sorting_newest(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_sorting_price_asc_and_desc(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_contact_for_price_hardened_privacy_audit(self, client, store_alpha, merchant_alpha):
        """
        Hardened privacy test: Uses unique sentinel values (e.g. 133742.00 / 199999.00).
        Asserts sentinel price NEVER appears in HTML, attributes, JSON, or scripts.
        Asserts item sorts at the very end (NULLS LAST) in both price_asc and price_desc.
        """
        ...
    def test_public_listing_invalid_sort_falls_back_to_newest(self, client, store_alpha):
        ...

    # 5. Discount Calculation Edge Cases
    def test_public_listing_discount_percentage_rounding_and_edge_cases(self, client, store_alpha, merchant_alpha):
        """Tests commercial half-up rounding, <1% suppression, and equal price/MRP."""
        ...

    # 6. Pagination & Query Preservation
    def test_public_listing_pagination_12_per_page(self, client, store_alpha, merchant_alpha):
        ...
    def test_public_listing_pagination_preserves_query_filters(self, client, store_alpha, merchant_alpha):
        """Asserts page navigation preserves q, category, availability, and sort parameters."""
        ...
    def test_public_listing_pagination_invalid_page_numbers(self, client, store_alpha, merchant_alpha):
        ...

    # 7. Image Fallbacks
    def test_public_listing_image_fallback_when_no_primary_image(self, client, store_alpha, merchant_alpha):
        """Uses first ordered gallery image if is_primary is False; uses placeholder if gallery empty."""
        ...

    # 8. Robust N+1 Query Count Prevention (Differential Guard)
    def test_public_listing_n_plus_one_prevention_differential(self, client, store_alpha, merchant_alpha):
        """
        Robust N+1 query prevention test:
        Compares query count when listing 1 product (Q1) vs 12 products (Q12).
        Asserts that query count remains O(1) constant: Q12 == Q1.
        Also enforces a generous ceiling (<= 10 queries) to ensure performance while
        remaining robust against legitimate middleware, session, or template tag additions.
        """
        ...

    # 9. Deferred Navigation Audit
    def test_public_listing_no_premature_product_detail_links(self, client, store_alpha, merchant_alpha):
        """Asserts product cards do NOT contain href='#' or /products/<slug>/ until Stage C4."""
        ...
```

### 7.2 Visual & Responsive QA Checklist
1. **Mobile (375px & 390px):** Two-column product grid with 3:4 aspect ratio cards. Native `<details>` filter drawer expands smoothly. Horizontal overflow assertion: `scrollWidth === clientWidth`.
2. **Tablet (768px):** 3-column grid layout with clean category pill navigation.
3. **Desktop (1440px):** 4-column grid layout with functional header search bar, inline sort dropdown, and elided pagination.

---

## 8. Implementation Steps & Milestones

Execution will proceed across these atomic steps upon receiving explicit authorization:

- **Step 1:** Enhance selector `get_public_storefront_products` in `apps/products/selectors.py` (preserving caller signature, implementing SQL `Case/When` nulling, and `-is_primary` image prefetch).
- **Step 2:** Add route in `apps/stores/urls.py` and implement view `public_product_list` in `apps/stores/views.py`.
- **Step 3:** Implement templates:
  - `templates/storefront/product_list.html`
  - `templates/storefront/partials/_product_card.html` (unlinked, display-only)
- **Step 4:** Integrate header search form in `templates/storefront/partials/_header.html` and homepage CTAs in `templates/stores/public_detail.html`.
- **Step 5:** Write comprehensive automated test suite `apps/stores/tests/test_storefront_listing_c3.py`.
- **Step 6:** Run test suite, dry-run migration checks, and ruff linting.
- **Step 7:** Perform Playwright multi-viewport responsive verification.
- **Step 8:** Submit completion report.

---

*This document is ready for review. Awaiting explicit user authorization before making any code modifications.*

