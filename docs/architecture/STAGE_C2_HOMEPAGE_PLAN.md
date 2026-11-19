# Stage C2 Implementation Plan — Public Store Homepage (Revision 2)

**Document:** `docs/architecture/STAGE_C2_HOMEPAGE_PLAN.md`  
**Stage:** C2 — Public Store Homepage (`/s/<store-slug>/`)  
**Status:** PROPOSED & PENDING HUMAN APPROVAL  
**Stitch Screens Reference:**  
- Screen 2: *Mobile Store Homepage — Krishna Garments* (ID: `43ec8b47c21f4fae986f14b63c13e7ef`, 780 × 5166 px)  
- Screen 6: *Store Homepage — Krishna Garments (Desktop)* (ID: `8fe5e14e7c9b4e7193b502725ad47e50`, 2560 × 7118 px)  

---

## 1. Executive Summary & Corrections Implemented

This revised Stage C2 implementation plan incorporates all human review feedback:

1. **Whitelisted Selector Ordering:** `get_public_storefront_products()` is restricted to an explicit ordering whitelist (`ALLOWED_PUBLIC_PRODUCT_ORDERING`). Arbitrary ordering strings are rejected.
2. **Strict Price Privacy for `CONTACT_FOR_PRICE`:** For any product with `price_display_mode == CONTACT_FOR_PRICE` (or where price is unassigned), price, MRP, and discount percentage are completely suppressed from the rendered HTML and client-visible data. Only "Contact for Price" is displayed.
3. **Clean Route Dependency Management (No Fake Stubs):** Neither fake views nor redirect stubs will be created in C2. C3 owns product listing and C4 owns product detail. Template links will use canonical URL paths `/s/{{ store.slug }}/products/` and `/s/{{ store.slug }}/products/?category={{ category.slug }}`. C3 and C4 will wire the named routes when authorized.
4. **Header Call Action Reuse:** C2 reuses the safe call action already implemented in the C1 header (`tel:{{ store.merchant.contact_number }}`). No phone normalization or WhatsApp helper is introduced in C2.
5. **Minimal Public Product Selector Update:** Reuses the exact prefetch behavior (`primary_images` and active `categories`) and structure of `get_public_storefront_products()`. Adds only whitelisted `ordering` defaulting to `"name"`.
6. **Graceful Handling of Missing Data:** Comprehensive fallback handling for missing product images (styled placeholder), missing categories (cleanly omitted badge), and unpriced items. Availability labels strictly match backend enum choices (`In Stock`, `Made to Order`, `Out of Stock`).
7. **Renamed to "Latest Products":** Replaced all references to "Featured Products" with "Latest Products" to reflect the actual mechanism (latest eight published products ordered by `-created_at`).
8. **Confirmed Zero Model or Migration Changes:** No fields, models, or migrations are introduced.

---

## 2. Architecture & Verified Backend Capabilities

### 2.1 Model Fields Verified (No Changes Needed)

| Domain Model | Code Location | Verified Fields Used | Invariant & Data Safety Rules |
|--------------|---------------|----------------------|-------------------------------|
| **`Store`** | `apps/stores/models.py:14-119` | `name`, `slug`, `tagline`, `description`, `logo`, `cover_image`, `status` | Publicly accessible ONLY if `status == PUBLISHED`. |
| **`Merchant`** | `apps/merchants/models.py:10-40` | `name`, `city`, `state`, `contact_number`, `email`, `status` | Publicly accessible ONLY if `status == ACTIVE`. Private fields (`id`, `address`, `pin_code`, `status`) strictly withheld. |
| **`Category`** | `apps/products/models.py:23-90` | `name`, `slug`, `image`, `display_order`, `is_active` | Strictly filtered by `merchant=store.merchant` and `is_active=True`. |
| **`Product`** | `apps/products/models.py:91-516` | `name`, `slug`, `sku`, `price`, `mrp`, `price_display_mode`, `availability_mode`, `discount_percentage`, `primary_image`, `status` | Strictly filtered by `merchant=store.merchant` and `status=PUBLISHED`. |
| **`ProductImage`** | `apps/products/models.py:554-585` | `image`, `is_primary`, `display_order` | Automatically prefetched via `Prefetch("images", queryset=ProductImage.objects.filter(is_primary=True), to_attr="primary_images")`. |

### 2.2 Reusable Existing Selectors & Planned Signature

#### Existing Store Selector:
`get_public_store_by_slug(slug: str) -> Store | None` in `apps/stores/selectors.py:10-33`.  
Strictly enforces `status=StoreStatus.PUBLISHED` and `merchant__status=MerchantStatus.ACTIVE`.

#### Existing Category Selector:
`get_merchant_categories(merchant: Merchant, include_inactive: bool = False) -> QuerySet[Category]` in `apps/products/selectors.py:56-71`.  
Returns active categories belonging strictly to this merchant, ordered by `display_order, name`.

#### Public Product Selector Extension:
Update `get_public_storefront_products()` in `apps/products/selectors.py`:
```python
ALLOWED_PUBLIC_PRODUCT_ORDERING = {
    "name": ("name",),
    "newest": ("-created_at",),
    "-created_at": ("-created_at",),
}

def get_public_storefront_products(
    merchant: Merchant,
    category_slug: str | None = None,
    ordering: str = "name",
) -> QuerySet[Product]:
    """
    Returns published products for customer-facing digital storefront browsing.
    Ordering parameter is strictly whitelisted.
    """
    if ordering not in ALLOWED_PUBLIC_PRODUCT_ORDERING:
        raise ValueError(
            f"Invalid ordering '{ordering}'. Allowed choices: {', '.join(sorted(ALLOWED_PUBLIC_PRODUCT_ORDERING.keys()))}"
        )

    if not merchant or merchant.status != MerchantStatus.ACTIVE:
        return Product.objects.none()

    store = getattr(merchant, "store", None)
    if not store or store.status != StoreStatus.PUBLISHED or not store.is_publicly_accessible:
        return Product.objects.none()

    order_by_fields = ALLOWED_PUBLIC_PRODUCT_ORDERING[ordering]

    qs = (
        Product.objects.filter(
            merchant=merchant,
            status=ProductStatus.PUBLISHED,
        )
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_images",
            ),
            Prefetch(
                "categories",
                queryset=Category.objects.filter(is_active=True),
            ),
        )
        .order_by(*order_by_fields)
    )

    if category_slug:
        category = Category.objects.filter(
            merchant=merchant,
            slug=category_slug.lower(),
            is_active=True,
        ).first()

        if not category:
            return Product.objects.none()

        qs = qs.filter(categories=category)

    return qs
```

---

## 3. Homepage Component Architecture & Layout

The template `templates/stores/public_detail.html` extends `storefront/base.html` and implements the Stitch-derived responsive layout:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Header (C1: Logo, Store Name, Tagline, Call Action)      │
├─────────────────────────────────────────────────────────────┤
│ 2. Hero Section:                                            │
│    - Configured Cover Image with gradient overlay OR        │
│      Branded Emerald Gradient Fallback                      │
│    - Store Name + Tagline + Safe Location Badge             │
│    - Dynamic Metric Badges (Products Count, Categories)     │
│    - Primary CTA: "Browse All Products"                     │
├─────────────────────────────────────────────────────────────┤
│ 3. Category Showcase ("Shop by Category"):                  │
│    - Responsive Grid (2-cols mobile -> 5-cols desktop)      │
│    - Category Image (with fallback category icon) + Name    │
│    - Links to /s/<store-slug>/products/?category=<cat-slug> │
│    - Gracefully hidden if merchant has 0 active categories  │
├─────────────────────────────────────────────────────────────┤
│ 4. Latest Products Grid (Latest 8 Published Items):         │
│    - Responsive Grid (2-cols mobile -> 4-cols desktop)      │
│    - Product Card:                                          │
│      * Primary image (with missing-image fallback)          │
│      * Availability Badge (In Stock, Made to Order, Out)    │
│      * Category badge (if associated)                       │
│      * Product Name (2-line clamp)                          │
│      * Pricing: Selling price + MRP + discount %            │
│        OR "Contact for Price" (ZERO numeric price leak)     │
├─────────────────────────────────────────────────────────────┤
│ 5. Browse All Products Banner / CTA:                        │
│    - Clean section linking to /s/<store-slug>/products/     │
├─────────────────────────────────────────────────────────────┤
│ 6. Store Story / Description:                               │
│    - Merchant-provided store.description prose (if set)     │
├─────────────────────────────────────────────────────────────┤
│ 7. Footer (C1: Merchant Info, Verified Social Links)        │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Handling Unfinished Routes (C3 & C4 Dependency Contract)
- **C3 owns the product listing implementation.**
- **C4 owns the product detail implementation.**
- To avoid introducing fake views or misleading redirect stubs that make incomplete features look finished:
  - Links to the catalogue listing will use the direct canonical path `/s/{{ store.slug }}/products/`.
  - Links to category filtered listing will use `/s/{{ store.slug }}/products/?category={{ category.slug }}`.
  - Product card links will link directly to `/s/{{ store.slug }}/products/` (or omit interaction) until C4 implements the detail page.
  - No fake view functions or redirect stubs will be added to `apps/stores/urls.py` or `views.py`.

### 3.2 Pricing & Privacy Rules in Template
```django
{% if product.price_display_mode == "CONTACT_FOR_PRICE" or not product.price %}
    <span class="text-xs sm:text-sm font-semibold text-primary">Contact for Price</span>
{% else %}
    <div class="flex items-baseline gap-1.5 flex-wrap">
        <span class="font-price font-bold text-sm sm:text-base text-on-surface">
            ₹{{ product.price|floatformat:0 }}
        </span>
        {% if product.mrp and product.mrp > product.price %}
            <span class="font-price text-xs text-on-surface-variant line-through">
                ₹{{ product.mrp|floatformat:0 }}
            </span>
            {% if product.discount_percentage %}
                <span class="font-badge text-[10px] font-bold text-error bg-error-container px-1.5 py-0.5 rounded-sm">
                    {{ product.discount_percentage }}% OFF
                </span>
            {% endif %}
        {% endif %}
    </div>
{% endif %}
```
- For `CONTACT_FOR_PRICE`: Price, MRP, and discount percentage are 100% absent from the rendered DOM, data attributes, and metadata.

### 3.3 Safe Fallbacks for Images and Categories
- **Store Cover Fallback:** If `store.cover_image` is missing, renders an elegant branded container (`bg-gradient-to-br from-primary via-primary-container to-teal-900`) with high-contrast text.
- **Product Image Fallback:** If `product.primary_images` is empty, renders a clean neutral placeholder box with an SVG shopping bag icon.
- **Category Badge:** Displayed only if `product.categories.all` contains active categories. Otherwise omitted.
- **Missing Categories:** If merchant has 0 categories, the "Shop by Category" section is cleanly suppressed.

---

## 4. Security & Tenant Isolation Matrix

| Invariant | Test Scenario | Expected Outcome |
|-----------|---------------|------------------|
| **Category Tenant Isolation** | Store A and Store B each have categories. | Accessing `/s/store-a/` only renders Store A's categories. Store B's categories never appear. |
| **Product Tenant Isolation** | Store A and Store B each have products. | Accessing `/s/store-a/` only renders Store A's products. Store B's products never appear. |
| **Draft & Archived Suppression** | Store A has DRAFT and ARCHIVED products alongside PUBLISHED products. | Only PUBLISHED products appear in Latest Products. |
| **Unpublished Store Inaccessibility** | Store has `status=DRAFT` or `UNPUBLISHED`. | Accessing `/s/<slug>/` returns **HTTP 404**. |
| **Inactive Merchant Inaccessibility** | Merchant has `status=SUSPENDED` or `INACTIVE`. | Accessing `/s/<slug>/` returns **HTTP 404**. |
| **Contact-for-Price Leak Prevention** | Product has `price_display_mode=CONTACT_FOR_PRICE` with a numeric `price` stored in DB. | Rendered HTML contains "Contact for Price". The numeric price does NOT appear anywhere in the response text or attributes. |
| **Sensitive Tenant Data Protection** | Inspect rendered homepage HTML for published store. | Does NOT contain `store.id`, `merchant.id`, street address, PIN code, or merchant status. |

---

## 5. Exact Files to be Modified or Created in Stage C2

Once authorized, implementation will touch **only** the following files:

1. **`apps/products/selectors.py`**
   - Add `ALLOWED_PUBLIC_PRODUCT_ORDERING` whitelist.
   - Add whitelisted `ordering: str = "name"` parameter to `get_public_storefront_products()`.
2. **`apps/stores/views.py`**
   - Update `public_store_detail` view to query active merchant categories, latest eight published products (ordered by `"-created_at"`), and total published product count.
3. **`templates/stores/public_detail.html`**
   - Replace temporary placeholder with the responsive Store Homepage layout extending `storefront/base.html`.
4. **`static/css/dist/styles.css`**
   - Recompile via `npm run build:css` to ensure any new responsive utility classes are included.
5. **`apps/stores/tests/test_storefront_homepage_c2.py`**
   - New unit and integration test suite verifying homepage sections, tenant isolation, price privacy, and empty state fallbacks.

**No other application files, models, or migrations will be modified.**

---

## 6. Verification Plan

1. **Automated Unit & Integration Tests:**
   - Run `apps/stores/tests/test_storefront_homepage_c2.py`.
   - Run full project test suite (`pytest`) to ensure all 467+ tests pass.
2. **Migration & Code Quality Verification:**
   - `python manage.py makemigrations --check --dry-run` (verify zero migrations).
   - `ruff check` (verify zero linting errors).
   - `ruff format --check apps config` (verify zero formatting drift).
3. **Visual QA Screenshots (Playwright):**
   - Capture full-page screenshots of `/s/<store-slug>/` at Mobile (375 × 667), Tablet (768 × 1024), and Desktop (1280 × 800) to confirm visual alignment with Stitch designs.
