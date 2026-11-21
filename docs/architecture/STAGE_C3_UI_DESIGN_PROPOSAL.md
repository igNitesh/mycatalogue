# Stage C3 Public Product Catalogue UI Design Specification (Revision 4)

**Document:** `docs/architecture/STAGE_C3_UI_DESIGN_PROPOSAL.md`  
**Stage:** C3 — Public Product Listing & Search Pipeline (`/s/<store-slug>/products/`)  
**Role:** Senior UI/UX Designer & Django Frontend Architect  
**Status:** PROPOSED & PENDING HUMAN APPROVAL  
**Branch:** `master`  
**Repository:** `igNitesh/mycatalogue`  
**Git HEAD Commit:** `86121fb2392e3696d1f92185525196edb7bb9beb`  

---

## 1. Codebase Verification & Environment Baseline

To ensure absolute documentation integrity, all architectural specifications in this document are directly grounded in the inspected checkout.

### 1.1 Inspected Files & Verified Capabilities
| Component | Inspected File | Verified Baseline & Capabilities |
| :--- | :--- | :--- |
| **Product Selector** | [`apps/products/selectors.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/products/selectors.py#L170-L270) | `get_public_storefront_products(merchant, category_slug=None, ordering="newest", *, search_query=None, availability_mode=None)`<br>• Prefetches gallery images ordered by `("-is_primary", "display_order", "created_at")` with `to_attr="primary_images"`.<br>• Applies SQL `Case/When` nulling for `PriceDisplayMode.CONTACT_FOR_PRICE` with `NULLS LAST` on price sorting.<br>• Filters search by `Q(name__icontains=q) \| Q(sku__icontains=q)`.<br>• Availability filter matches uppercase `clean_avail in AvailabilityMode.values`. |
| **Storefront Listing View** | [`apps/stores/views.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/stores/views.py#L57-L140) | `public_product_list(request, slug)`<br>• Context keys provided: `store`, `categories`, `page_obj`, `paginator`, `total_published_count`, `search_query`, `selected_category`, `selected_category_slug`, `selected_availability`, `selected_sort`, `base_query_string`, `has_active_filters`.<br>• Strips and uppercases `availability` from GET params.<br>• Validates sort against `{"newest", "price_asc", "price_desc"}` (defaults to `"newest"`).<br>• Paginates at 12 items/page.<br>• Preserves query parameters across pagination via `base_query_string`. |
| **Domain Models & Choices** | [`apps/products/models.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/products/models.py)<br>[`apps/products/choices.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/products/choices.py) | • `AvailabilityMode`: `IN_STOCK` ("In Stock"), `MADE_TO_ORDER` ("Made to Order"), `OUT_OF_STOCK` ("Out of Stock").<br>• `PriceDisplayMode`: `SHOW_PRICE` ("Show Price"), `CONTACT_FOR_PRICE` ("Contact for Price").<br>• `ProductImage`: `image`, `is_primary`, `display_order`, `created_at`.<br>• `Product.custom_attributes`: `models.JSONField(default=dict, blank=True)`. |
| **Storefront Templates** | [`templates/storefront/base.html`](file:///c:/Users/nites/Desktop/mycatalogue/templates/storefront/base.html)<br>[`templates/storefront/partials/_header.html`](file:///c:/Users/nites/Desktop/mycatalogue/templates/storefront/partials/_header.html) | • Base template includes Tailwind CSS and HTMX (`js/vendor/htmx.min.js`). Zero external UI frameworks (no Alpine.js, Bootstrap, or React).<br>• Header provides brand identity, store contact phone, and centralized search input wired to `stores:public_products?q=...`. |
| **Automated Test Suite** | [`apps/stores/tests/test_storefront_listing_c3.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/stores/tests/test_storefront_listing_c3.py) | **500 passed, 2 warnings in 14.99s** (`pytest`). Full test suite is completely green. |

---

## 2. Updated Page Hierarchy

The Public Product Catalogue page follows this exact top-to-bottom visual and functional hierarchy across all screen sizes:

```
+---------------------------------------------------------------------------------------+
| 1. STOREFRONT HEADER (Existing shared partial: _header.html)                          |
|    - Brand logo, Store Name, Tagline / City location, Call button                     |
+---------------------------------------------------------------------------------------+
| 2. STOREFRONT SEARCH INPUT (Integrated inside _header.html)                           |
|    - Sole search bar on page; wired to stores:public_products?q=...                   |
|    - NO duplicate search input rendered in the catalogue page body                     |
+---------------------------------------------------------------------------------------+
| 3. HORIZONTAL CATEGORY NAVIGATION ROW                                                 |
|    - Rendered immediately beneath header branding when categories exist               |
|    - Snap-scroll horizontal pill row: [All Products] [Category A] [Category B]...     |
|    - Preserves active search query, availability, and sort parameters                 |
+---------------------------------------------------------------------------------------+
| 4. BREADCRUMB NAVIGATION (Top-Left)                                                   |
|    - Placed top-left, directly under the horizontal category navigation row           |
|    - Minimalist hierarchy: Home > Catalogue [ > Selected Category ]                   |
+---------------------------------------------------------------------------------------+
| 5. PRODUCT HEADING & MATCHING RESULT COUNT                                            |
|    - Heading text: Selected Category Name, or Search Query, or "All Products"         |
|    - Verified count: Uses paginator.count (e.g. "28 items" or "12 items")             |
+---------------------------------------------------------------------------------------+
| 6. ONE HORIZONTAL TOOLBAR (Exactly two controls)                                      |
|    - Left: Sort by Control (Newest | Price: Low to High | Price: High to Low)          |
|    - Right: Filter Control (Availability-only filter trigger with badge)              |
|    - NO permanent left filter sidebar on desktop or mobile                            |
+---------------------------------------------------------------------------------------+
| 7. ACTIVE FILTER CHIPS ROW (Rendered ONLY when search, category, or availability active)
|    - [Search: "katan" x] [Category: Silk Sarees x] [Availability: In Stock x]         |
|    - NO Sort chip (sort is already visible in the toolbar control)                    |
|    - Explicit Clear All action: [Clear All Filters]                                   |
+---------------------------------------------------------------------------------------+
| 8. RESPONSIVE PRODUCT GRID                                                            |
|    - Desktop: 3 to 4 column responsive grid                                           |
|    - Mobile: Strict 2-column grid                                                     |
|    - Simplified cards: image, name, price/contact for price, restrained status badge  |
|    - Unlinked in Stage C3 (no detail navigation until Stage C4)                       |
+---------------------------------------------------------------------------------------+
| 9. PAGINATION BAR                                                                     |
|    - Filter-preserving page navigation using base_query_string                         |
+---------------------------------------------------------------------------------------+
```

---

## 3. Scope Boundaries & Unsupported Feature Removal

To keep MyCatalogue clean, minimal, and professional, the following elements are **strictly excluded** from Stage C3:

1. **WhatsApp Assistance Banner Removed**:
   - The conversational WhatsApp assistance banner previously proposed at the bottom of the feed is completely removed. Direct merchant enquiry will be architected in Stage C4 on individual product pages.
2. **Customer Account / Profile Navigation Removed**:
   - Customer profile / account icons and navigation are omitted. Storefront remains an unauthenticated public browsing experience.
3. **Customer Reviews and Ratings Excluded**:
   - No star ratings, customer review counts, or review submission widgets. No rating models exist in the backend schema.
4. **Unsupported E-Commerce Features Excluded**:
   - No cart, checkout, delivery estimation, shipping calculation, inventory counters ("Only 2 left!"), discount percentage badges, or payment buttons.
5. **Custom Attribute Filters Excluded**:
   - Merchant-defined custom attributes (`text`, `number`, `single_select`, `multi_select`, `color`) stored in `Product.custom_attributes` are NOT filterable in C3.
   - No filters for size, color, fabric, brand, or material.

---

## 4. Desktop Layout Specification (PC / Laptop: $\ge$ 1024px)

```
=========================================================================================
HEADER: [Logo] Alpha Silks      [ Search kurtas, sarees... ]    (Mumbai) [Call Store]
=========================================================================================
CATEGORY ROW: [ All Products ]  [ Silk Sarees ]  [ Cotton Sarees ]  [ Bridal Wear ]
-----------------------------------------------------------------------------------------
Home > Catalogue > Silk Sarees

Silk Sarees  (28 items)

+---------------------------------------------------------------------------------------+
| Sort by: [ Newest First          v ]                            [ Filter (1) | tune ] |
+---------------------------------------------------------------------------------------+
Active filters: [ Category: Silk Sarees x ] [ Availability: In Stock x ]  Clear all

+--------------------+  +--------------------+  +--------------------+  +---------------+
| +----------------+ |  | +----------------+ |  | +----------------+ |  | +-----------+ |
| | [In Stock]     | |  | | [Made to Order]| |  | |                | |  | |           | |
| |                | |  | |                | |  | |                | |  | |           | |
| | 3:4 Image      | |  | | 3:4 Image      | |  | | 3:4 Image      | |  | | 3:4 Image | |
| |                | |  | |                | |  | |                | |  | |           | |
| +----------------+ |  | +----------------+ |  | +----------------+ |  | +-----------+ |
| Banarasi Katan     |  | Pure Chanderi Saree|  | Tussar Raw Silk    |  | Kanjeevaram | |
| ₹4,999             |  | Contact for Price  |  | ₹8,499             |  | ₹12,999     | |
+--------------------+  +--------------------+  +--------------------+  +---------------+

+---------------------------------------------------------------------------------------+
| [Previous]                        [ 1 ]  2   3                                 [Next] |
+---------------------------------------------------------------------------------------+
```

### Desktop Design Specifications:
1. **Full-Width Catalogue Canvas**:
   - Spans `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6`.
   - **Zero permanent left sidebar**: The former 3-column filter sidebar is eliminated, allowing product images to take center stage.
2. **Subheader Removal**:
   - The former `<!-- Subheader Location & Ledger Bar -->` is completely removed.
3. **Top-Left Breadcrumbs**:
   - Positioned immediately beneath the category navigation row at top-left (`text-xs font-medium text-secondary`).
4. **Single Horizontal Toolbar**:
   - Bordered card container (`bg-surface-container-lowest border border-outline-variant/25 rounded-2xl p-2.5 sm:p-3 flex items-center justify-between shadow-xs`).
   - **Left**: Sort by select dropdown (`w-48 sm:w-56`).
   - **Right**: Filter button (`px-3.5 py-2 rounded-xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/30 text-xs font-semibold`).
   - If an availability filter is active, the button renders `Filter (1)`.
5. **Anchored Availability Popover**:
   - Clicking/focusing the Filter button toggles a clean, compact popover anchored directly beneath the button (`absolute right-0 top-full mt-2 w-64 bg-surface-container-lowest border border-outline-variant/30 rounded-2xl shadow-lg p-3 z-30`).
   - Contains Availability radio options, Apply button, and Clear link.
6. **Product Grid Density**:
   - 3 or 4 columns based on viewport width (`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5 lg:gap-6`).

---

## 5. Mobile Layout Specification (Mobile: $<$ 768px)

```
=========================================================================================
MOBILE HEADER: [Logo] Alpha Silks                           [ Search Icon ]  [ Phone ]
=========================================================================================
CATEGORY ROW (Horizontal Snap): [ All Products ]  [ Silk Sarees ]  [ Cotton ] ->
-----------------------------------------------------------------------------------------
Home > Catalogue

All Products (28 items)

+---------------------------------------------------------------------------------------+
| [ Sort: Newest     v ]                                            [ Filter (1) | = ]  |
+---------------------------------------------------------------------------------------+
Active filters: [ In Stock x ]  Clear all

+-----------------------------+  +-----------------------------+
| +-------------------------+ |  | +-------------------------+ |
| | [In Stock]              | |  | |                         | |
| |                         | |  | |                         | |
| | 3:4 Image (Touch Aspect)| |  | | 3:4 Image (Touch Aspect)| |
| |                         | |  | |                         | |
| +-------------------------+ |  | +-------------------------+ |
| Banarasi Katan Silk         |  | Pure Chanderi Saree         |
| ₹4,999                      |  | Contact for Price           |
+-----------------------------+  +-----------------------------+
| +-------------------------+ |  | +-------------------------+ |
| | [Made to Order]         | |  | | [Out of Stock]          | |
| | 3:4 Image               | |  | | 3:4 Image               | |
| +-------------------------+ |  | +-------------------------+ |
| Tussar Silk Saree           |  | Organza Floral Print        |
| ₹8,499                      |  | ₹3,200                      |
+-----------------------------+  +-----------------------------+

+---------------------------------------------------------------------------------------+
| [< Prev]                       Page 1 of 3                           [Next >]         |
+---------------------------------------------------------------------------------------+
```

### Mobile Design Specifications:
1. **Strict Two-Column Product Grid**:
   - Exactly 2 columns (`grid grid-cols-2 gap-2.5 sm:gap-3.5`).
   - 3:4 portrait image ratio optimized for touch viewports.
2. **Simplified Product Cards**:
   - No category micro-label, no SKU, no discount badges, no ratings.
   - Clean product name (truncated to 2 lines) and legible price.
3. **Single Two-Control Toolbar**:
   - Spans full screen width.
   - Left: Compact sort selector (`h-9 text-xs rounded-xl`).
   - Right: Filter trigger button (`h-9 text-xs rounded-xl`).
4. **Accessible Expandable Panel (Zero JS Dependencies)**:
   - Built cleanly using the native HTML5 `<details class="relative">` / `<summary class="list-none">` disclosure pattern.
   - Avoids simulating complex JavaScript modal dialogs with focus trapping and backdrops without external libraries.
   - When tapped, it smoothly expands an inline filter form within the document flow directly below the toolbar.
   - Native browser support handles keyboard navigation, screen reader `aria-expanded` state, and form submission without custom JavaScript or third-party packages.

---

## 6. Exact Sort by Control Specification

### Placement & Visual Structure
- **Location**: Left side of the single horizontal toolbar.
- **Visual Presentation**:
  - Desktop: Label `"Sort by:"` followed by styled `<select>` element.
  - Mobile: Compact `<select>` element with `expand_more` icon.

### Allowed Options & Backend Mapping
The control exposes strictly the 3 sorting options supported by `apps/products/selectors.py`:

| Display Label | Value Parameter | Backend Selector Ordering | Behavior |
| :--- | :--- | :--- | :--- |
| **Newest** (Default) | `newest` | `-created_at` | Shows latest added products first. |
| **Price: Low to High** | `price_asc` | `effective_public_price.asc(nulls_last=True), -created_at` | Lowest priced items first. Contact-for-price items placed strictly at end (`NULLS LAST`). |
| **Price: High to Low** | `price_desc` | `effective_public_price.desc(nulls_last=True), -created_at` | Highest priced items first. Contact-for-price items placed strictly at end (`NULLS LAST`). |

### State & Query Preservation Contract
- Changing the sort control submits a GET form preserving:
  - `q`: Active search query.
  - `category`: Active category slug.
  - `availability`: Active availability filter.
- **Page Reset**: Changing sort automatically resets `page` to 1 (omits `page` from URL).
- **Invalid Input Fallback**: Tampered sort values (e.g. `?sort=popular`) are caught in `apps/stores/views.py` and safely default to `"newest"` with HTTP 200.

---

## 7. Exact Filter Menu & GET Form Contract

### Filter Scope: Availability Only
The Filter menu contains **strictly** the product availability options supported by the backend:

```html
<!-- Availability Filter Form Contract -->
<form method="get" action="{% url 'stores:public_products' slug=store.slug %}" class="space-y-3">
    <!-- Preserved Active Context (Hidden Inputs) -->
    {% if search_query %}
        <input type="hidden" name="q" value="{{ search_query }}">
    {% endif %}
    {% if selected_category_slug %}
        <input type="hidden" name="category" value="{{ selected_category_slug }}">
    {% endif %}
    {% if selected_sort and selected_sort != "newest" %}
        <input type="hidden" name="sort" value="{{ selected_sort }}">
    {% endif %}
    <!-- Note: "page" is intentionally omitted to reset pagination to page 1 -->

    <div class="flex items-center justify-between pb-2 border-b border-outline-variant/20">
        <span class="text-xs font-bold text-on-surface">Availability</span>
        {% if selected_availability %}
            <a href="{% url 'stores:public_products' slug=store.slug %}?{% if search_query %}q={{ search_query|urlencode }}&{% endif %}{% if selected_category_slug %}category={{ selected_category_slug }}&{% endif %}{% if selected_sort != 'newest' %}sort={{ selected_sort }}{% endif %}" class="text-[11px] font-semibold text-primary hover:underline">
                Clear
            </a>
        {% endif %}
    </div>

    <!-- Radio Options -->
    <div class="space-y-1.5 text-xs">
        <!-- All Products (Clears availability filter) -->
        <label class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-container-low cursor-pointer">
            <input type="radio" name="availability" value="" {% if not selected_availability %}checked{% endif %} class="text-primary focus:ring-primary">
            <span class="text-on-surface">All Products</span>
        </label>

        <!-- In Stock -->
        <label class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-container-low cursor-pointer">
            <input type="radio" name="availability" value="in_stock" {% if selected_availability == "IN_STOCK" %}checked{% endif %} class="text-primary focus:ring-primary">
            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span class="text-on-surface">In Stock</span>
        </label>

        <!-- Made to Order -->
        <label class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-container-low cursor-pointer">
            <input type="radio" name="availability" value="made_to_order" {% if selected_availability == "MADE_TO_ORDER" %}checked{% endif %} class="text-primary focus:ring-primary">
            <span class="w-2 h-2 rounded-full bg-amber-500"></span>
            <span class="text-on-surface">Made to Order</span>
        </label>

        <!-- Out of Stock -->
        <label class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-container-low cursor-pointer">
            <input type="radio" name="availability" value="out_of_stock" {% if selected_availability == "OUT_OF_STOCK" %}checked{% endif %} class="text-primary focus:ring-primary">
            <span class="w-2 h-2 rounded-full bg-slate-400"></span>
            <span class="text-on-surface">Out of Stock</span>
        </label>
    </div>

    <!-- Actions -->
    <div class="pt-2 border-t border-outline-variant/20 flex items-center gap-2">
        <button type="submit" class="flex-1 py-2 px-3 bg-primary text-on-primary font-bold text-xs rounded-xl shadow-xs hover:bg-primary-container transition-colors">
            Apply Filter
        </button>
    </div>
</form>
```

### Filter Interaction Rules:
1. **Active Filter Count on Trigger Button**:
   - Represents the selected availability filter **only**.
   - If `selected_availability` is active (`IN_STOCK`, `MADE_TO_ORDER`, or `OUT_OF_STOCK`), the button renders `Filter (1)` with a primary pill indicator.
   - If no availability filter is selected, the button renders `Filter` without a count badge.
2. **Apply Action**:
   - Submits `availability=<value>`, retaining hidden `q`, `category`, and `sort`.
   - Automatically resets `page` to 1.
3. **Clear Availability Action**:
   - Directly links to the URL omitting `availability`, retaining `q`, `category`, and `sort`.
4. **Invalid Value Fallback**:
   - If a user passes an unrecognized availability value (e.g. `?availability=unknown`), `apps/stores/views.py` sets `availability_mode = None`, safely falling back to displaying all products without throwing an error (HTTP 200).

---

## 8. Active Filter Chips & Clear-All Behavior

### Active Chips Specification
Active chips appear in a clean row below the toolbar **strictly** when one or more of the following three filters are active:
1. **Search Query** (`q`): `[Search: "katan" (x)]`
2. **Category** (`category`): `[Category: Silk Sarees (x)]`
3. **Availability** (`availability`): `[In Stock (x)]`

> [!IMPORTANT]
> **NO Sort Chip**: In accordance with user feedback, a Sort chip is NOT rendered. The active sort order is already prominently displayed within the Sort by control on the toolbar.

```html
<!-- Active Chips Container -->
{% if search_query or selected_category or selected_availability %}
    <div class="flex items-center gap-2 flex-wrap text-xs pt-1">
        <span class="text-secondary font-medium">Active filters:</span>

        {% if search_query %}
            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container text-on-surface font-medium">
                <span>Search: "{{ search_query }}"</span>
                <a href="{% url 'stores:public_products' slug=store.slug %}?{% if selected_category_slug %}category={{ selected_category_slug }}&{% endif %}{% if selected_availability %}availability={{ selected_availability|lower }}&{% endif %}{% if selected_sort != 'newest' %}sort={{ selected_sort }}{% endif %}" class="text-outline hover:text-on-surface" aria-label="Remove search filter">
                    <span class="material-symbols-outlined text-[14px]">close</span>
                </a>
            </span>
        {% endif %}

        {% if selected_category %}
            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container text-on-surface font-medium">
                <span>Category: {{ selected_category.name }}</span>
                <a href="{% url 'stores:public_products' slug=store.slug %}?{% if search_query %}q={{ search_query|urlencode }}&{% endif %}{% if selected_availability %}availability={{ selected_availability|lower }}&{% endif %}{% if selected_sort != 'newest' %}sort={{ selected_sort }}{% endif %}" class="text-outline hover:text-on-surface" aria-label="Remove category filter">
                    <span class="material-symbols-outlined text-[14px]">close</span>
                </a>
            </span>
        {% endif %}

        {% if selected_availability %}
            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container text-on-surface font-medium">
                <span>{{ selected_availability|title }}</span>
                <a href="{% url 'stores:public_products' slug=store.slug %}?{% if search_query %}q={{ search_query|urlencode }}&{% endif %}{% if selected_category_slug %}category={{ selected_category_slug }}&{% endif %}{% if selected_sort != 'newest' %}sort={{ selected_sort }}{% endif %}" class="text-outline hover:text-on-surface" aria-label="Remove availability filter">
                    <span class="material-symbols-outlined text-[14px]">close</span>
                </a>
            </span>
        {% endif %}

        <!-- Explicit Clear All Action -->
        <a href="{% url 'stores:public_products' slug=store.slug %}{% if selected_sort != 'newest' %}?sort={{ selected_sort }}{% endif %}" class="text-primary hover:underline font-semibold ml-1">
            Clear all
        </a>
    </div>
{% endif %}
```

### Deterministic Clear-All Contract:
- Clicking **"Clear all"** cleanly resets all active filters (`q`, `category`, `availability`, and `page`), navigating to:
  `{% url 'stores:public_products' slug=store.slug %}{% if selected_sort != 'newest' %}?sort={{ selected_sort }}{% endif %}`
- If sorting has been customized (e.g. `price_asc`), sort order is preserved as a user viewing preference; otherwise, it returns to the clean base URL.
- Zero stale query parameters are retained.

---

## 9. Simplified Product Card Specification

```
+---------------------------------------+
| [Restrained Availability Dot / Badge] |
|                                       |
|                                       |
|        3:4 Portrait Image             |
|        (prefetched primary image)     |
|                                       |
|                                       |
+---------------------------------------+
| Product Title (1-2 lines bold)        |
| ------------------------------------- |
| ₹4,999                                |
| [ Or: Contact for Price ]             |
+---------------------------------------+
```

### Verified Card Elements:
1. **Product Image Container**:
   - Uniform `aspect-[3/4]` portrait container (`w-full bg-surface-container-low overflow-hidden relative rounded-2xl`).
   - Non-critical images use native lazy loading (`loading="lazy"`).
2. **Deterministic Image Fallback Rule**:
   - **Rule**: Render the first image from the verified ordered prefetched collection:
     `product.primary_images.0.image.url`
   - **Fallback**: If `product.primary_images` is empty, render the neutral accessible placeholder:
     ```html
     <div class="w-full h-full flex flex-col items-center justify-center text-outline/40 bg-surface-container-low" aria-hidden="true">
         <span class="material-symbols-outlined text-4xl">inventory_2</span>
         <span class="text-[10px] text-outline font-medium mt-1">No Image Available</span>
     </div>
     ```
   - **No secondary DB query**: Calling `product.primary_image` property is strictly forbidden in template loops as it causes $O(N)$ N+1 queries.
3. **Product Name**:
   - Clean, readable typography: `<h2 class="font-headline font-bold text-xs sm:text-sm text-on-surface line-clamp-2">`.
   - SKU and Category labels are **omitted from the default card** to prevent clutter.
4. **Price or Contact for Price**:
   - If `price_display_mode == "CONTACT_FOR_PRICE"` or `not product.price`:
     - Renders solely `"Contact for Price"` (`text-primary font-bold text-xs sm:text-sm`).
     - **Zero numerical leakage**: Never renders numeric price, MRP, compare-at price, or discount percentages.
   - If `price_display_mode == "SHOW_PRICE"`:
     - Displays selling price: `₹{{ product.price|floatformat:0 }}` (`font-price font-bold text-sm sm:text-base text-on-surface`).
     - Strikethrough MRP and discount badges are omitted to keep cards image-focused and minimal.
5. **Restrained Availability Indicator (Optional / Subtle)**:
   - Subtle indicator in top-left corner:
     - `IN_STOCK`: Subtle dot indicator with "In Stock" text.
     - `MADE_TO_ORDER`: Subtle amber badge with "Made to Order".
     - `OUT_OF_STOCK`: Subtle slate badge with "Out of Stock".
6. **Unlinked in Stage C3**:
   - No `<a>` tags with `/products/<slug>/` or placeholder `href="#"`. The cards remain unlinked display cards in Stage C3.

---

## 10. Clarified Product Counts

To prevent contradictions between the heading count and the visible product grid, three distinct counts are defined:

| Context Variable | Source | Semantic Meaning | Placement & Purpose |
| :--- | :--- | :--- | :--- |
| **`paginator.count`** | `Paginator(products_qs, 12).count` | **Matching Products Count**: Total count of published products matching the currently active search, category, and availability filters. | **Rendered in the Product Heading Block**: e.g., `Silk Sarees (28 items)`. Always reflects the exact count of filtered results. |
| **`page_obj.object_list\|length`** | Current page slice | **Page Item Count**: Number of products rendered on the currently visible page (e.g. 12 on page 1, 4 on page 2). | Used for screen-reader live announcements (e.g., "Showing 12 products on page 1"). |
| **`total_published_count`** | `Product.objects.filter(merchant=merchant, status=PUBLISHED).count()` | **Total Store Catalogue Count**: Total unfiltered published products for this merchant across all categories. | **Used EXCLUSIVELY in template conditionals** to differentiate the empty catalogue state (`total_published_count == 0`) from a no-results filter state (`total_published_count > 0 and paginator.count == 0`). NEVER displayed in the results heading. |

---

## 11. Custom Attribute Scope Decision

### Background
MyCatalogue supports merchant-defined custom attributes in `Product.custom_attributes` (JSONField) across five types:
- `text`
- `number`
- `single_select`
- `multi_select`
- `color`

### Architectural Decision for C3
**All custom attributes are strictly excluded from C3 filtering and product cards.**

### Rationale:
1. **Merchant Heterogeneity**: Custom attributes vary widely by merchant domain. Guessing or generating automatic filters from unstructured JSON causes poor UX and SQL performance penalties.
2. **Clean Scope Boundary with Stage C4**:
   - Custom attributes will be presented on the **Product Detail Page (Stage C4)** in a structured Specifications table with type-aware formatting.
   - Future attribute-based filtering will be designed in a separate phase allowing merchants to curate which attributes are filterable.

---

## 12. Empty and Error States

The page differentiates between an empty catalogue and filtered empty states:

| Scenario | Condition | UI Presentation | Actions Provided |
| :--- | :--- | :--- | :--- |
| **Empty Catalogue** | `total_published_count == 0` | Friendly editorial card: *"Catalogue Coming Soon — Our digital catalogue is currently being curated. Please check back soon for our latest arrivals."* | Button: `[Back to Store Home]` |
| **Search Returned 0 Matches** | `search_query` active and `paginator.count == 0` | Search-specific empty card: *"No products found matching '{{ search_query }}'. Try checking your spelling or using different keywords."* | Button: `[Clear Search]`<br>Button: `[Store Home]` |
| **Filter Returned 0 Matches** | `category` or `availability` active and `paginator.count == 0` | Filter-specific empty card: *"No Matching Products — No products match your selected filter criteria. Try adjusting your filters."* | Button: `[Clear All Filters]`<br>Button: `[Store Home]` |
| **Missing Product Image** | `product.primary_images` is empty | Neutral placeholder box with `inventory_2` icon and "No Image Available". | Presentation fallback |
| **Invalid Filter Parameter** | Malformed `availability` or `sort` | Silently normalizes to safe default (e.g. `newest` or all availability). Returns HTTP 200. | All standard catalogue actions |
| **Invalid Category Slug** | Non-existent or cross-tenant slug | Returns HTTP 200 with clean Filter Returned 0 Matches empty state. | Button: `[Clear All Filters]` |

---

## 13. Accessibility Considerations

1. **Semantic HTML Structure**:
   - `<nav aria-label="Breadcrumb">` for top-left breadcrumbs.
   - `<nav aria-label="Category navigation">` for horizontal category row.
   - `<main>` for primary catalogue content.
   - `<article>` with `data-product-id` for each product card.
   - `<nav aria-label="Catalogue pagination">` for pagination bar.
2. **Expandable Panel & Popover Accessibility**:
   - Uses native HTML5 `<details>` and `<summary>` for the mobile expandable panel, ensuring built-in browser keyboard interaction (`Space` / `Enter` to expand/collapse) and accessible state announcements.
   - Desktop popover uses explicit `role="dialog"` and `aria-label="Filter products by availability"`.
   - Radio buttons include explicit `<label>` tags with visible focus outlines (`focus:ring-2 focus:ring-primary`).
3. **Screen Reader Content & Contrast**:
   - Product images carry meaningful `alt="{{ product.name }}"`.
   - Fallback placeholders have `aria-hidden="true"`.
   - "Contact for Price" text is fully readable by assistive technologies.
   - Active filter dismiss buttons carry explicit `aria-label="Remove [Filter Name] filter"`.
   - All body and metadata text satisfies WCAG 2.1 AA contrast ratios ($\ge 4.5:1$).

---

## 14. Files Expected to Change During Implementation

When authorized to implement, only the following files will be modified:

1. **[`templates/storefront/product_list.html`](file:///c:/Users/nites/Desktop/mycatalogue/templates/storefront/product_list.html)**:
   - Remove subheader location bar.
   - Remove permanent left sidebar.
   - Remove duplicate in-page search input.
   - Position breadcrumbs at top-left under category row.
   - Implement product heading + matching result count (`paginator.count`).
   - Implement single 2-control toolbar (Sort by on left, Filter on right).
   - Implement anchored Availability popover (desktop) and native `<details>` expandable panel (mobile).
   - Render active filter chips row below toolbar (Search, Category, Availability; NO Sort chip).
   - Implement responsive product grid (3-4 cols desktop, 2 cols mobile).
   - Remove WhatsApp assistance banner and profile elements.
2. **[`templates/storefront/partials/_product_card.html`](file:///c:/Users/nites/Desktop/mycatalogue/templates/storefront/partials/_product_card.html)**:
   - Implement simplified card (image, name, price/contact for price, restrained availability).
   - Enforce single deterministic image fallback (`product.primary_images.0` $\rightarrow$ neutral placeholder).
   - Remove SKU and category labels from default card.
   - Remove discount percentage badges and strikethrough MRP.
   - Maintain strict `CONTACT_FOR_PRICE` privacy and unlinked C3 boundary.
3. **[`apps/stores/tests/test_storefront_listing_c3.py`](file:///c:/Users/nites/Desktop/mycatalogue/apps/stores/tests/test_storefront_listing_c3.py)**:
   - Update tests to verify absence of sidebar, 2-control toolbar, availability-only popover/panel, active filter chips, absence of Sort chip, and sentinel price privacy.

---

## 15. Revision 4 Change Log

| Item | Previous Revision 3 | Corrected Revision 4 Decision | Rationale |
| :--- | :--- | :--- | :--- |
| **WhatsApp Assistance Banner** | Included at bottom of feed (`<!-- WhatsApp Assistance Banner -->`). | **Completely removed from C3.** | Direct merchant enquiry will be architected on individual product pages in Stage C4. |
| **Customer Profile / Account** | Mockups showed customer profile avatar. | **Completely removed.** | Storefront is an unauthenticated public browsing experience. |
| **Active Sort Chip** | Rendered `[Sort: Price Low to High (x)]` chip. | **Sort chip removed.** Only Search, Category, and Availability chips are rendered. | The selected sort option is already prominently displayed inside the Sort by control. Duplicating it in the chips row caused visual clutter. |
| **Mobile Filter Interaction** | Proposed slide-over modal drawer with backdrop. | **Simplified to native HTML5 `<details>` expandable panel.** | Avoids unverified claims of pure HTML/Tailwind focus trapping and modal backdrops without external JS. Native `<details>` provides 100% accessible zero-dependency interaction. |
| **Product Card Complexity** | Displayed category label, SKU, strikethrough MRP, and commercial discount badge. | **Simplified default card:** Image, Name, Price / Contact for Price, and subtle availability indicator. | Keeps cards image-focused, minimal, and professional without marketplace clutter. |
| **Image Fallback Rule** | Mentioned two fallbacks (`prefetched_images.0` $\rightarrow$ `primary_image` property $\rightarrow$ placeholder). | **One deterministic rule:** `product.primary_images.0` $\rightarrow$ neutral placeholder. | Inspected `apps/products/selectors.py`: images are prefetched with `to_attr="primary_images"`. Calling `.primary_image` would cause an N+1 query. |
| **Result Count Clarification** | Vaguely referenced "item count". | **Explicitly clarified:** Product heading displays `paginator.count` (matching products count); `total_published_count` is reserved strictly for the empty catalogue conditional. | Prevents displaying a total catalogue count that contradicts visible filtered results. |
| **Filter Button Active Count** | Counted any active filter. | **Filter button count reflects availability filter only:** `Filter (1)`. | Categories are selected in the horizontal row and search is in the header; the Filter button controls availability only. |

---

*This revised specification is complete, fully verified against backend code, and ready for human review.*  
*Awaiting explicit human developer approval before modifying any code or templates.*
