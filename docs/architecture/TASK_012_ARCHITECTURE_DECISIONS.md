# Task 012 — Architecture Decisions & Data Model Specification

**Project:** MyCatalogue — Digital Storefront SaaS  
**Document:** Architecture Decisions & Data Model Specification  
**Current Version:** Revision 3 (Final Consistency & Production Verification)  
**Status:** FINAL AUTHORITATIVE SPECIFICATION FOR HUMAN APPROVAL  
**Author:** AI Pair Programmer (Antigravity)  
**Date:** 2026-11-18  
**Preceding Task:** Task 011 — Stitch Design Audit & UI-to-Domain Mapping  
**Implementation Authorization:** STRICTLY NO CODE MODIFICATIONS UNTIL APPROVED  

---

## Document Revision History

| Revision | Date | Author | Summary of Changes & Audit Notes |
| :---: | :---: | :---: | :--- |
| **0.1** | 2026-11-18 | AI Pair Programmer | Initial architecture specification draft based on Task 011 Stitch Design Audit. |
| **1.0** | 2026-11-18 | AI Pair Programmer | **Revision 1 (Human Review Corrections):**<br>- Addressed naive property replacement of `is_available` with Expand & Contract.<br>- Replaced `is_price_hidden` with `PriceDisplayMode` enum.<br>- Decoupled attribute backend data contract (Task 013) from UI builder (Task 019).<br>- Audited `Merchant` vs `Store` field ownership; rejected duplicate address.<br>- Reclassified Printable A4 QR poster to Milestone 2; retained dynamic QR endpoint.<br>- Replaced latency claims with query budgets. |
| **2.0** | 2026-11-18 | AI Pair Programmer | **Revision 2 (Final Architecture Verification):**<br>- Audited all 33 `is_available` references across 12 classifications.<br>- Verified `Category.display_order` already exists in `apps/products/models.py`.<br>- Specified multi-tier pricing validation.<br>- Reconciled Stitch screens (dashboard only; hero covers suffice).<br>- Decoupled Task 019 from Task 018. |
| **3.0** | 2026-11-18 | AI Pair Programmer | **Revision 3 (Final Consistency & Production Verification):**<br>1. **Availability Write-Path Synchronization:** Defined exact deterministic behavior for all `save(update_fields=...)` variations, `save()` without update fields (instance change tracking), new instances, and direct assignments. Explicitly covered bypass paths (`bulk_create`, `bulk_update`, fixtures). Mandated database `CheckConstraint` `chk_prod_avail_mode_sync` preventing desynchronization.<br>2. **Multi-Tier Pricing Validation Clarification:** Disentangled `full_clean()`, `clean_fields()`, `clean()`, service validation, and database constraints. Specified handling of invalid choices, draft vs published rules, and `ROUND_HALF_UP` discount rounding.<br>3. **Reconciled WhatsApp Fallback:** Added explicit `allow_whatsapp_fallback = models.BooleanField(default=True)` to `Store`, harmonizing model, migrations, and UI settings.<br>4. **QR Caching vs Revocation Reality:** Replaced inaccurate instant-revocation claims with an exact analysis of origin 404 vs browser/CDN cache TTLs (reduced to 1 hour / 3600s).<br>5. **Authoritative Index Inventory:** Consolidated overlapping indexes into a single query-justified compound index (`idx_prod_mcht_mode_created`). Eliminated redundant slug and low-cardinality indexes.<br>6. **Custom Attribute & Social Validation Contract:** Fully specified allowed fields per type, explicit boolean rejection in numbers (`not isinstance(v, bool)`), key normalization, social platform allowlist, and HTTPS URL validation.<br>7. **Deployment & Migration Accuracy:** Grounded migration in PostgreSQL metadata updates and transactional data backfills; removed unsupported zero-lock assertions.<br>8. **Realistic Query Budgets:** Established expected query counts (4 and 5) with defensive upper-bound test budgets ($\le 5$ and $\le 6$). |

---

## 1. Executive Summary

This document establishes the authoritative, implementation-ready architectural specification for **MyCatalogue**, converting the findings and UI mappings of **Task 011 (Stitch Design Audit)** into concrete engineering plans.

MyCatalogue is a multi-tenant digital catalogue SaaS designed specifically for local brick-and-mortar merchants (apparel boutiques, jewellery workshops, electronics retailers, organic food stores, and artisanal producers). The platform operates two distinct operational surfaces:
1. **Merchant Management Dashboard (`/merchants/`)**: Authenticated, role-governed back-office administration where merchants curate products, categorize inventory, organize image galleries, and configure digital storefront identities.
2. **Public Storefront (`/s/<store_slug>/`)**: Fast, responsive, publicly accessible, read-only digital showcase optimized for mobile shoppers, enabling product discovery, rich visual inspection, and high-conversion WhatsApp enquiry generation without transactional shopping carts or checkout gateways.

Following an exhaustive audit of the existing codebase (`apps/merchants`, `apps/stores`, `apps/products`), this document resolves **five pivotal architectural decisions**, establishes a strict boundary between **MVP requirements** and **deferred features**, formalizes the **data model evolution**, defines the **public storefront routing and security topology**, and specifies a **phased 9-task implementation roadmap (Task 013 to Task 021)**.

### Architectural Governance Principles
- **Existing Implementation:** Respected and preserved as the foundation. No gratuitous rewrites or duplicate fields.
- **Proposed Changes:** Formulated with minimal disruption, high backward compatibility, and strict tenant isolation.
- **Approved Decisions:** Clearly identified as consensus baselines.
- **Open Decisions:** Explicitly highlighted for human decision and authorization.

---

## 2. Repository Findings & Discrepancies Against Task 011

A rigorous line-by-line inspection of the live Django codebase against the Task 011 audit document revealed several critical discrepancies and confirmed existing infrastructure that must be leveraged without duplication:

| Feature / Domain | Task 011 Audit Assumption | Actual Codebase Reality | Architectural Impact & Resolution |
| :--- | :--- | :--- | :--- |
| **Category `display_order`** | Assumed missing or requiring addition. | `apps/products/models.py` (lines 47–51) **already implements** `display_order = models.PositiveIntegerField(default=0, db_index=True)`, ordering `["display_order", "name"]`, and compound index `idx_cat_mcht_active_order`. | **Existing Implementation.** Remove duplicate field proposal. No schema migration required for Category. |
| **Public Storefront Selectors** | Assumed missing or requiring from-scratch implementation. | `apps/products/selectors.py` already implements `get_public_storefront_products()` (lines 160–214), enforcing merchant ACTIVE and product PUBLISHED filters. `apps/stores/selectors.py` implements `get_public_store_by_slug()`. | **Existing Implementation.** Do not recreate selectors. Extend existing selectors in Task 015 to support category slug filtering, pagination, and multi-mode availability badges. |
| **Out-of-Stock Product Visibility** | Assumed out-of-stock products might be filtered out of public views. | The codebase and automated test suite (`apps/products/tests/test_public_visibility.py`, line 62) explicitly assert that products with `is_available=False` **must remain visible** on public storefronts with an out-of-stock badge. | **Approved Decision.** Invariant confirmed: stock status never controls catalogue discoverability; it controls inventory badges and enquiry CTA states. |
| **Store Branding Assets** | Assumed store branding models or image fields were missing. | `apps/stores/models.py` already possesses `logo` (ImageField) and `cover_image` (ImageField), complete with upload validators and management forms in `apps/stores/forms.py`. | **Existing Implementation.** Leverage existing `logo` and `cover_image`. No additional banner models or image fields required. |
| **Merchant vs Store Address** | Proposed adding physical address to `Store`. | `apps/merchants/models.py` already implements `address`, `city`, `state`, and `pin_code`. `Store` is a 1-to-1 extension of `Merchant`. | **Corrected Proposal.** `Merchant` authoritatively owns physical location. Do not duplicate address columns on `Store`. |
| **Custom Attribute Structure** | Suggested supporting scalar and multi-select values seamlessly. | `apps/products/validators.py` (`validate_attributes()`, lines 94–105) explicitly rejects non-scalar values (`list`, `dict`), enforcing `key: str/int/float/bool`. | **Proposed Change.** Multi-select, single-select, and colour swatch attributes require an expanded JSON validator schema in Task 013 while retaining `models.JSONField(default=dict)`. |
| **QR Code Library** | Assumed dynamic generation is trivial with existing libraries. | Dependency audit (`pip list` in `.venv`) revealed `pillow` (v12.1.1) is installed, but `qrcode` is **not installed**. | **Approved Decision.** In-memory QR code generation placed in Task 020 after adding `qrcode>=8.0` to `requirements.txt`. |
| **Analytics Telemetry** | Stitch Dashboard mock showcased visitor counts, WhatsApp clicks, and views. | No telemetry models, tables, tracking pixels, or analytics pipelines exist anywhere in the application. | **Approved Decision.** Telemetry will NOT be faked with random numbers. Analytics is formally **deferred to Milestone 3**; dashboard cards will display real inventory KPIs and a neutral "Coming Soon" note. |

---

## 3. Final MVP Scope Recommendation & Roadmap Boundaries

To ensure rapid, robust, and secure delivery of MyCatalogue, features are classified into three strictly governed operational horizons:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MYCATALOGUE MVP SCOPE BOUNDARIES                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  HORIZON A: MVP CORE CATALOGUE (Prioritized for Immediate Implementation)   │
│  - Store Identity (Name, Slug, Description, Tagline, Social Links)          │
│  - Store Branding (Existing Logo & Cover Image)                             │
│  - Multi-image Product Gallery (up to 8 images per product)                 │
│  - Three-tier Availability Mode (IN_STOCK, MADE_TO_ORDER, OUT_OF_STOCK)     │
│  - Dual Pricing (Selling Price + Optional MRP + Dynamic Discount %)         │
│  - Explicit Price Display Mode (SHOW_PRICE vs CONTACT_FOR_PRICE)            │
│  - Structured Custom Attributes Data Contract (text, num, select, color)    │
│  - Merchant Attribute Form Builder UI (Back-Office Form in Task 019)        │
│  - Category Presentation with existing display ordering                     │
│  - Public Storefront Home, Category Grid, and Product Detail Pages          │
│  - WhatsApp Direct Enquiry Action (with explicit Store toggle fallback)     │
│  - Dynamic In-Memory Storefront QR Code endpoint (PNG with 1hr caching)     │
│  - Real Dashboard Catalogue Health KPIs (Zero Fake Stats)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  HORIZON B: MILESTONE 2 — OPERATIONAL IMPROVEMENTS (Post-MVP Deferral)      │
│  - Printable A4 Merchandising QR Posters with customizable branding         │
│  - CSV Bulk Product Import / Export                                         │
│  - Bulk Inventory Inline Quick-Editing Table                                │
│  - Faceted Storefront Attribute Search & Filtering (PostgreSQL GIN)         │
│  - In-browser Image Crop and Aspect Ratio Presets                           │
│  - Physical removal of legacy database column `is_available`                │
├─────────────────────────────────────────────────────────────────────────────┤
│  HORIZON C: MILESTONE 3 — GROWTH & ADVANCED PLATFORM (Future Roadmap)       │
│  - Edge Analytics Pipeline (views, unique sessions, click telemetry)        │
│  - Shopper Wishlists & Social Sharing Metrics                               │
│  - WhatsApp Business Cloud API automated inventory sync                     │
│  - Multi-location Store Inventory Allocation                                │
│  - Subscription Billing & Tier Quota Enforcement                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Five Architectural Decision Analyses

---

### Decision 1: Product Availability Representation & Deterministic Write-Path Synchronization

#### Context & Problem
The Stitch designs depict three practical inventory states:
1. `In Stock` (Immediate fulfillment)
2. `Made to Order` (Custom fabrication / tailoring / bake-on-order)
3. `Out of Stock` (Temporarily unavailable)

Currently, `apps/products/models.py` uses a binary boolean:
```python
is_available = models.BooleanField(
    default=True,
    db_index=True,
    help_text="Controls catalogue availability (e.g., out of stock vs in stock).",
)
```

#### Complete Repository Write-Path & Call-Site Audit
An exhaustive search across the entire codebase identified **33 references across 11 files**, classified by their operational write/read mechanics:

| Classification | File & Line | Code Context / Invocation Pattern | Write or Read? | Transition Handling |
| :--- | :--- | :--- | :---: | :--- |
| **Model Definition** | `apps/products/models.py:138` | `is_available = models.BooleanField(...)` | Definition | Retained physically in DB during Phase 1/2. |
| **Compound Index** | `apps/products/models.py:182` | `models.Index(fields=["merchant", "status", "is_available"], ...)` | Definition | Retained during transition; consolidated index added. |
| **Migration History** | `apps/products/migrations/0001_initial.py:51, 112` | Schema creation & index creation | Historical | Untouched. |
| **ORM Direct Create** | `apps/products/services.py:130` | `Product.objects.create(..., is_available=True)` | **Write** | Updated in Task 013 to pass `availability_mode="IN_STOCK", is_available=True`. |
| **Service Signature** | `apps/products/services.py:161` | `def update_product_profile(..., is_available: bool = _UNSET)` | Signature | Updated in Task 013 to accept `availability_mode: str = _UNSET, is_available: bool = _UNSET`. |
| **Service Write** | `apps/products/services.py:207–208` | `if is_available is not _UNSET: product.is_available = bool(is_available)` | **Write** | Synchronizes both fields according to precedence rules. |
| **Direct Assignment** | `apps/products/tests/test_public_visibility.py:69` | `product.is_available = False` | **Write** | Handled by model-level synchronization in `Product.save()`. |
| **`update_fields` Write**| `apps/products/tests/test_public_visibility.py:70` | `product.save(update_fields=["is_available"])` | **Write** | `Product.save()` intercepts `update_fields` and adds `availability_mode`. |
| **Admin List Display** | `apps/products/admin.py:36` | `list_display = (..., "is_available", ...)` | Read | Migrated to `availability_mode` in Task 013. |
| **Admin Filter** | `apps/products/admin.py:39` | `list_filter = ("status", "is_available", ...)` | ORM Read | Migrated to `availability_mode` in Task 013. |
| **Form Definition** | `apps/products/forms.py:112` | `is_available = forms.BooleanField(...)` | Form Def | Maintained in Task 013; migrated to 3-choice radio/select in Task 019. |
| **View Form Processing**| `apps/products/views.py:209, 213` | `if not form.cleaned_data.get("is_available"): update_product(..., is_available=False)` | **Write** | Dual-write service translates seamlessly. Migrated in Task 019. |
| **View Initial Mapping**| `apps/products/views.py:263` | `"is_available": product.is_available` | Read | Maintained via column. Migrated in Task 019. |
| **View Form Update** | `apps/products/views.py:305` | `is_available=form.cleaned_data.get("is_available", True)` | **Write** | Dual-write service translates seamlessly. Migrated in Task 019. |
| **Template Checkbox** | `templates/products/form.html:226–233` | Checkbox input, labels, errors | Read | Maintained in Task 013; replaced in Task 019. |
| **Template Table Badges**| `templates/products/partials/product_table.html:87, 203` | `{% if p.is_available %}`, `{% if not p.is_available %}` | Read | Updated in Task 013 to display 3 distinct status badges. |
| **Selector Docstring** | `apps/products/selectors.py:171` | Note on visibility invariant | Doc | Updated in Task 013. |
| **Test Assertions** | `test_models.py:70`, `test_services.py:56, 132`, `test_public_visibility.py:75`, `test_views.py:528` | `assert product.is_available is ...` | Read | Maintained; extended to assert `availability_mode`. |
| **Test Service Writes** | `test_services.py:127` | `update_product_profile(..., is_available=False)` | **Write** | Continues to pass through dual-write backward compatibility. |
| **Test Form POSTs** | `test_views.py:515, 540, 620` | `{"is_available": "on"}` | **Write** | Continues to pass; updated in Task 019. |

#### Deterministic Write-Path Synchronization Contract
To prevent silent overwrites and eliminate guessing during writes, the system enforces the following deterministic synchronization contract across all write paths:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 DETERMINISTIC AVAILABILITY WRITE SPECIFICATION              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. `save(update_fields=["availability_mode"])`:                             │
│    - Caller declared `availability_mode` as target.                         │
│    - Model computes: `self.is_available = (self.availability_mode !=        │
│      AvailabilityMode.OUT_OF_STOCK)`.                                       │
│    - Model automatically expands `update_fields` to include `"is_available"`│
│      so both database columns are updated in SQL.                           │
│                                                                             │
│ 2. `save(update_fields=["is_available"])`:                                  │
│    - Caller declared `is_available` as target (e.g. legacy tests).          │
│    - Model computes: `self.availability_mode = AvailabilityMode.IN_STOCK    │
│      if self.is_available else AvailabilityMode.OUT_OF_STOCK`.              │
│    - Model automatically expands `update_fields` to include                 │
│      `"availability_mode"` so both database columns are updated in SQL.     │
│                                                                             │
│ 3. `save(update_fields=["availability_mode", "is_available"])`:             │
│    - Caller provided both fields in `update_fields`.                        │
│    - Model checks coherence: If `(self.availability_mode != OUT_OF_STOCK)   │
│      != self.is_available`: raises `ValidationError("Contradictory values:  │
│      availability_mode conflicts with is_available.")`.                     │
│    - If coherent: persists both fields.                                     │
│                                                                             │
│ 4. `save()` without `update_fields` (Full Instance Save):                   │
│    - For New Instances (`self._state.adding is True`):                      │
│      • If `availability_mode` is set (non-default) and `is_available` is    │
│        default: sync `is_available = (mode != OUT_OF_STOCK)`.               │
│      • If `is_available` is explicitly False and `availability_mode` is     │
│        default: sync `availability_mode = OUT_OF_STOCK`.                    │
│      • If both set coherently: persist. If contradictory: raise `Validation`│
│    - For Existing Instances (`self._state.adding is False`):                │
│      • Model tracks initial values loaded from DB (`_initial_mode`,         │
│        `_initial_is_available`).                                            │
│      • If only `is_available` was mutated in Python: sync `mode`.           │
│      • If only `availability_mode` was mutated in Python: sync `is_avail`.  │
│      • If both were mutated coherently: persist.                            │
│      • If both were mutated contradictorily: raise `ValidationError`.       │
│                                                                             │
│ 5. Direct Service-Layer Writes (`create_product` & `update_product_profile`):│
│    - Authoritative application write path.                                  │
│    - If caller provides both parameters with conflicting values, service    │
│      explicitly raises `ValidationError` rather than guessing intent.       │
│                                                                             │
│ 6. Bulk & Direct SQL Bypass Protection (`CheckConstraint`):                 │
│    - `QuerySet.update()`, `bulk_create()`, `bulk_update()`, fixtures, and   │
│      raw SQL bypass Django's `Model.save()`.                                │
│    - To enforce absolute database consistency, Task 013 introduces a hard   │
│      PostgreSQL/SQLite constraint:                                          │
│      `chk_prod_avail_mode_sync`:                                            │
│      `(availability_mode = 'OUT_OF_STOCK' AND is_available = FALSE) OR`     │
│      `(availability_mode IN ('IN_STOCK', 'MADE_TO_ORDER') AND is_avail=TRUE)│
│    - Any bulk update attempting to desynchronize columns is aborted by DB.  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Call Sites Migrated in Task 013 vs Deferred to Task 019
- **Must Be Migrated in Task 013:**
  - `apps/products/models.py`: add `availability_mode`, model-level `save()` interceptor, initial tracking, and `chk_prod_avail_mode_sync`.
  - `apps/products/services.py`: update `create_product()` and `update_product_profile()` signatures and synchronization logic.
  - `apps/products/selectors.py`: update `get_public_storefront_products()` and catalogue queries to filter/annotate by `availability_mode`.
  - `apps/products/admin.py`: update `list_display` and `list_filter` to use `availability_mode`.
  - `templates/products/partials/product_table.html`: update table badges to display "In Stock", "Made to Order", and "Out of Stock".
  - `apps/products/tests/`: add test coverage for all 3 modes and dual-write conflict rejection.
- **Deferred to Task 019 (Merchant UI):**
  - `apps/products/forms.py` (`ProductForm`): replacing the single checkbox with a 3-option radio or select widget.
  - `templates/products/form.html`: rendering the new availability widget.
  - `apps/products/views.py`: processing the new form widget. (During Tasks 013–018, the existing form continues submitting `is_available`, which the dual-write service translates safely).

---

### Decision 2: Product Pricing Semantics & Multi-Tier Validation

#### Context & Problem
Merchants sell items with two distinct commercial intents:
1. `SHOW_PRICE`: Fixed selling prices, optionally compared against an anchor MRP with an auto-computed discount.
2. `CONTACT_FOR_PRICE`: Bespoke, variable, high-end, or made-to-order merchandise where public prices are concealed and shoppers are prompted to enquire.

Redundant boolean flags (`is_price_hidden`) are rejected in favor of an explicit domain enum:
```python
# apps/products/choices.py
class PriceDisplayMode(models.TextChoices):
    SHOW_PRICE = "SHOW_PRICE", "Show Price"
    CONTACT_FOR_PRICE = "CONTACT_FOR_PRICE", "Contact for Price"
```

#### Authoritative Multi-Tier Validation Architecture
To prevent invalid combinations from ever reaching the database, MyCatalogue distinguishes and enforces validation across **independent tiers**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 MULTI-TIER PRICING VALIDATION ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. TIER 1: DOMAIN SERVICE LAYER (`validators.py` / `services.py`)          │
│    - Enforces workflow invariants before any ORM persistence:               │
│      • Permission verification (`_check_permission`).                       │
│      • In `publish_product()`: strictly enforces that if                    │
│        `price_display_mode == SHOW_PRICE`, then `price is not None`.        │
│      • In `create_product()` & `update_product_profile()`: validates        │
│        pricing rules via `validate_product_pricing(...)`.                   │
│                                                                             │
│ 2. TIER 2: MODEL INTEGRITY LAYER (`clean_fields`, `clean`, `save`)          │
│    - `clean_fields()`: Validates field choices (rejects invalid strings for │
│      `price_display_mode`), decimal precision, and `MinValueValidator(0)`.  │
│    - `clean()`: Cross-field business logic:                                 │
│      • Enforces `mrp >= price` whenever both are provided.                  │
│      • Enforces `price >= 0` and `mrp >= 0`.                                │
│    - `save()`: Explicitly invokes `self.clean_fields()` and `self.clean()`  │
│      before persisting, ensuring direct ORM saves enforce all constraints   │
│      (bypassed only when `raw=True` during fixture loading).                │
│                                                                             │
│ 3. TIER 3: DATABASE CONSTRAINT LAYER (PostgreSQL & SQLite CheckConstraints) │
│    - Storage-engine integrity constraints:                                  │
│      • `chk_prod_price_mode_valid`: `price_display_mode IN ('SHOW_PRICE',   │
│        'CONTACT_FOR_PRICE')`                                                │
│      • `chk_prod_price_non_neg`: `price IS NULL OR price >= 0`              │
│      • `chk_prod_mrp_non_neg`: `mrp IS NULL OR mrp >= 0`                    │
│      • `chk_prod_mrp_gte_price`: `mrp IS NULL OR price IS NULL OR mrp>=price`│
│      • `chk_prod_pub_price`: `status != 'PUBLISHED' OR                      │
│        price_display_mode != 'SHOW_PRICE' OR price IS NOT NULL`             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Draft vs Published Pricing Rules
- **In `DRAFT` status:** A product with `price_display_mode = SHOW_PRICE` **may be saved with `price = None`** (allowing merchants to draft items before final pricing is known).
- **In `PUBLISHED` status:** The publishing transition service (`publish_product()`) and the database `chk_prod_pub_price` constraint strictly enforce that `price` **must not be None** when `price_display_mode == SHOW_PRICE`.

#### Data Migration of Legacy Null Prices
- If `price is not None`: data migration sets `price_display_mode = PriceDisplayMode.SHOW_PRICE`.
- If `price is None` and `status == ProductStatus.PUBLISHED`: data migration sets `price_display_mode = PriceDisplayMode.CONTACT_FOR_PRICE` (preserving live customer-facing behavior).
- If `price is None` and `status == ProductStatus.DRAFT`: data migration sets `price_display_mode = PriceDisplayMode.SHOW_PRICE` (standard retail default; draft status safely permits `price=None` until publication).

#### Discount Percentage Integer Rounding Rule
The discount percentage is computed purely on-the-fly and never stored:
```python
from decimal import Decimal, ROUND_HALF_UP

@property
def discount_percentage(self) -> int | None:
    """
    Computes integer discount percentage using standard commercial half-up rounding.
    Returns None if:
      - price_display_mode != SHOW_PRICE
      - price or mrp is missing
      - mrp <= price
      - mrp <= 0
      - calculated discount is less than 1% (avoids misleading '0% OFF' badges)
    """
    if (
        self.price_display_mode == PriceDisplayMode.SHOW_PRICE
        and self.price is not None
        and self.mrp is not None
        and self.mrp > self.price
        and self.mrp > 0
    ):
        raw_discount = ((self.mrp - self.price) / self.mrp) * Decimal("100")
        rounded = int(raw_discount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return rounded if rounded >= 1 else None
    return None
```

---

### Decision 3: Analytics & Telemetry Handling

#### Context & Problem
The Stitch "Merchant Overview Dashboard" screen features prominent mock metric cards (Storefront Visits: `2,840`, Product Views: `9,120`, WhatsApp Inquiries: `94`).

No telemetry collection pipeline exists in MyCatalogue.

#### Evaluated Options & Ethical Decision
- **Option A (Simulate Fake Numbers): REJECTED.** Violates engineering standards and platform trust. Merchants making inventory replenishment decisions based on fabricated visitor metrics would be actively harmed.
- **Option B (Implement Ad-Hoc Analytics Table in MVP): REJECTED.** Relational database write contention on public GET requests, bot filtering complexity, and privacy compliance (DPDP/GDPR) represent premature operational complexity.
- **Option C (Defer Analytics; Display Truthful Inventory KPIs): APPROVED.**

#### Approved Resolution
1. **MVP Action (Task 018):**
   - Replace simulated telemetry cards with **Real Catalogue Health Metrics** already present in the database:
     - **Total Active Products** (`Product.objects.filter(merchant=merchant, status='PUBLISHED').count()`)
     - **Out of Stock Inventory Count** (`...availability_mode='OUT_OF_STOCK'`)
     - **Active Categories Count** (`Category.objects.filter(merchant=merchant, is_active=True).count()`)
     - **Storefront Live Status** (`Store.status == 'PUBLISHED'`) with a one-click button to view the public storefront.
   - Display a neutral, stylish "Storefront Analytics — Coming Soon" banner explaining that visitor telemetry and WhatsApp conversion tracking will be introduced in an upcoming release.
2. **Milestone 3 Roadmap:**
   - Build an asynchronous event-streaming pipeline (Redis buffer / Celery or Cloud PubSub $\rightarrow$ ClickHouse or nightly aggregated roll-up tables).

---

### Decision 4: Storefront QR Code Generation & Cache Invalidation Reality

#### Context & Problem
Merchants need QR codes to display on shop counters, display windows, and product packaging to drive in-store footfall to their digital catalogue (`/s/<store_slug>/`).

#### Operational Reality: Caching vs Endpoint Revocation
If a public endpoint `/s/<store_slug>/qr/` serves images with HTTP caching headers, the architectural behavior across layers must be documented truthfully:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   QR ENDPOINT CACHING & REVOCATION MATRIX                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Origin Server (Django Application):                                      │
│    - If `Store.status != PUBLISHED` or `Merchant.status != ACTIVE`:         │
│      The origin view IMMEDIATELY returns HTTP 404.                          │
│    - Un-published or draft stores are rejected on the origin immediately.   │
│                                                                             │
│ 2. Reverse-Proxy / Shared Edge Cache (CDN):                                 │
│    - To balance origin load against revocation latency, the endpoint sets:  │
│      `Cache-Control: public, max-age=3600, stale-while-revalidate=300`       │
│      (1 hour TTL instead of 24 hours).                                      │
│    - If a store is unpublished, an edge cache will serve the cached image   │
│      until the 1-hour TTL expires (or until an explicit CDN purge is called)│
│                                                                             │
│ 3. Client Browser Cache:                                                    │
│    - A user's browser that previously downloaded the image retains it in    │
│      local browser cache for up to 1 hour without contacting the server.    │
│                                                                             │
│ 4. Authenticated Merchant Back-Office Preview:                              │
│    - Route: `/merchants/store/qr/preview/`                                  │
│    - Uncached (`Cache-Control: no-cache, no-store`).                        │
│    - Permits merchant preview and PNG download even while store is DRAFT.   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Storage Impact
Zero database rows, zero files written to disk or media storage.

---

### Decision 5: Complete Custom Attribute & Social Links Validation Contract

#### Context & Problem
Local merchants sell heterogeneous merchandise:
- Apparel: Size (`S, M, L, XL`), Fabric (`Cotton, Silk`), Fit (`Regular, Slim`), Color swatches.
- Jewellery: Purity (`22K, 18K`), Metal (`Yellow Gold, Rose Gold`), Stone (`Diamond, Ruby`).
- Electronics: Warranty (`1 Year`), Storage (`128GB, 256GB`), Connectivity (`Bluetooth 5.3`).

`apps/products/models.py` currently contains:
```python
attributes = models.JSONField(
    default=dict,
    blank=True,
    help_text="Custom product specifications and key-value attributes.",
)
```

#### Detailed Validation Rules by Field Type

```json
{
  "specifications": [
    {
      "key": "fabric",
      "label": "Fabric Material",
      "type": "single_select",
      "options": ["Pure Silk", "Organic Linen", "Combed Cotton"],
      "value": "Pure Silk"
    },
    {
      "key": "sizes",
      "label": "Available Sizes",
      "type": "multi_select",
      "options": ["XS", "S", "M", "L", "XL", "XXL"],
      "values": ["M", "L", "XL"]
    },
    {
      "key": "colors",
      "label": "Available Colors",
      "type": "color",
      "values": [
        {"name": "Midnight Blue", "hex": "#191970"},
        {"name": "Earthy Olive", "hex": "#556b2f"}
      ]
    },
    {
      "key": "thread_count",
      "label": "Thread Count",
      "type": "number",
      "value": 400,
      "unit": "TC"
    },
    {
      "key": "care_instructions",
      "label": "Care Instructions",
      "type": "text",
      "value": "Dry clean only."
    }
  ]
}
```

#### Strict Field Allowlist & Type Rules
Any unexpected field not present in the allowlist for that type raises `ValidationError`:

| Type | Strict Allowed Fields | Validation Rules & Constraints |
| :--- | :--- | :--- |
| **Global Contract** | `specifications: list[dict]` | - Max **15 specifications** per product.<br>- Every item must have unique `key` matching `^[a-z0-9_]{2,30}$`. Duplicate keys rejected.<br>- `label`: String, 2 to 50 characters, trimmed.<br>- `type`: Must be one of `['text', 'number', 'single_select', 'multi_select', 'color']`. Unknown types rejected. |
| **`single_select`** | `key`, `label`, `type`, `options`, `value` | - `options`: List of 1 to 20 strings (each 1–50 chars). Duplicate options rejected.<br>- `value`: Must be non-empty string and **must be present in `options`**. |
| **`multi_select`** | `key`, `label`, `type`, `options`, `values` | - `options`: List of 1 to 30 strings (each 1–50 chars). Duplicate options rejected.<br>- `values`: List of 1 to 20 selected strings.<br>- Every element in `values` **must be present in `options`**.<br>- Duplicate selected values in `values` are rejected.<br>- Empty strings inside `values` are rejected. |
| **`number`** | `key`, `label`, `type`, `value`, `unit` (optional) | - `value`: Numeric (`int` or `float`). Bounded between `-1,000,000,000` and `1,000,000,000`.<br>- **Boolean Rejection:** In Python, `isinstance(True, int)` is True. The validator explicitly enforces `if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValidationError`.<br>- `unit`: Optional string (max 15 characters, e.g. `g`, `cm`, `TC`). |
| **`text`** | `key`, `label`, `type`, `value` | - `value`: Non-empty string, maximum 500 characters. |
| **`color`** | `key`, `label`, `type`, `values` | - `values`: List of 1 to 15 color objects.<br>- Each object allows only `name` (1–30 chars) and `hex` (`^#[0-9a-fA-F]{6}$`).<br>- Duplicate `hex` or `name` rejected. |

#### Legacy Flat Dictionary Normalization & Collision Handling
- If `Product.attributes` is a legacy flat dict (e.g. `{"Fabric": "Linen"}` without `"specifications"`):
  - Normalization rule: keys are converted via `.strip().lower().replace("-", "_")`.
  - **Collision handling:** If two legacy keys normalize to the same slug (e.g. `"Fabric"` and `"fabric"`), the validator rejects the payload with `ValidationError("Duplicate attribute key after normalization: 'fabric'.")`.
  - In storefront presentation, legacy flat dicts are auto-coerced into `text` specifications for seamless rendering.

#### `Store.social_links` Validation Contract
```json
{
  "instagram": "https://instagram.com/krishnagarments",
  "facebook": "https://facebook.com/krishnagarments",
  "website": "https://krishnagarments.com"
}
```
- **Allowlist of Platforms:** Only keys in `{"instagram", "facebook", "youtube", "twitter_x", "pinterest", "website"}` are permitted. Any other key raises `ValidationError`.
- **URL Scheme & Format:** Every value must be a valid HTTPS URL validated via Django's `URLValidator(schemes=["https"])`. Insecure `http://` or malformed URLs raise `ValidationError`. Empty values are stripped.

---

## 5. Store & Merchant Domain Model Ownership & Stitch Evidence Reconciliation

### Reconciliation of Available Stitch Evidence
A rigorous recheck of the Stitch project assets confirms:
1. **Scope of Available Designs:** The Stitch project (`6403466717281225322`) contains Screens 1, 2, 3, and 4. All four screens depict the **Merchant Management Dashboard** (Product Inventory, Product Form, Overview Dashboard). No public storefront screens are provided in Stitch.
2. **Storefront Hero Evidence:** In the merchant dashboard (Screen 4 and Screen 1), the store is presented with its name, logo avatar, and cover image.
3. **Banner Management Finding:** The Stitch designs **contain zero evidence of multi-banner promotional carousels or independently scheduled promotional banners**. Proposing a separate `StoreBanner` model or carousel infrastructure would invent unverified functionality.
4. **Resolution:** The existing `Store.cover_image` (ImageField) is completely sufficient as the hero banner background for the public storefront home. Any requirement for rotating or promotional banners is classified as **UNRESOLVED / DEFERRED to future milestones**.

### Authoritative Domain Ownership Matrix

| Field / Information | Authoritative Owner | Existing Codebase Location | Architectural Decision & Rationale |
| :--- | :--- | :--- | :--- |
| **Store Name** | `Store` | `Store.name` | **Existing.** Authoritative name of public digital storefront. |
| **Store Slug** | `Store` | `Store.slug` | **Existing.** Authoritative unique URL identifier (`/s/<slug>/`). |
| **Description** | `Store` | `Store.description` | **Existing.** Store-specific marketing overview (max 1000 chars). |
| **Logo** | `Store` | `Store.logo` | **Existing.** Uploaded ImageField; satisfies Stitch circular avatar. |
| **Cover Image** | `Store` | `Store.cover_image` | **Existing.** Uploaded ImageField; satisfies storefront hero banner. |
| **Tagline** | `Store` | *None* | **Proposed on Store.** Short marketing slogan (max 120 chars). |
| **Social Links** | `Store` | *None* | **Proposed on Store.** JSONField with HTTPS URL validation. |
| **WhatsApp Number** | `Store` | *None* | **Proposed on Store.** Optional dedicated storefront mobile enquiry number. |
| **WhatsApp Fallback Toggle** | `Store` | *None* | **Proposed on Store.** `allow_whatsapp_fallback = BooleanField(default=True)`. If True and `whatsapp_number` is blank, falls back to `Merchant.contact_number`. |
| **Physical Address** | `Merchant` | `Merchant.address`, `city`, `state`, `pin_code` | **Existing on Merchant.** **REJECTED on Store.** Duplicating address is an anti-pattern. Storefront renders `store.merchant.address`. |
| **Business Phone** | `Merchant` | `Merchant.contact_number` | **Existing on Merchant.** Authoritative corporate registration contact. |
| **Category Ordering** | `Category` | `Category.display_order` | **Existing on Category.** Verified in `apps/products/models.py:47`. Duplicate field proposal removed. |

---

## 6. Recommended Data Model Changes

All proposed model adjustments are summarized below. Every change is non-destructive, backward-compatible, and tenant-isolated.

### A. App: `apps.products` — Model: `Product`

| Field Name | Type | Constraints / Choices | Default | Null / Blank | Index | Architectural Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `availability_mode` | `CharField` | `max_length=20`, `AvailabilityMode.choices` | `"IN_STOCK"` | `False / False` | **Part of Compound** | 3-state inventory model (`IN_STOCK`, `MADE_TO_ORDER`, `OUT_OF_STOCK`). |
| `price` | `DecimalField` | `max_digits=12`, `decimal_places=2`, `MinValueValidator(0)` | `None` | `True / True` | No | Existing field. Mandatory when `status=PUBLISHED` and `price_display_mode=SHOW_PRICE`. |
| `mrp` | `DecimalField` | `max_digits=12`, `decimal_places=2`, `MinValueValidator(0)` | `None` | `True / True` | No | Optional Maximum Retail Price for anchor comparison and discount computation. |
| `price_display_mode` | `CharField` | `max_length=20`, `PriceDisplayMode.choices` | `"SHOW_PRICE"` | `False / False` | **No** | Explicit price presentation mode. Low cardinality; separate index omitted. |
| `attributes` | `JSONField` | Standard JSONField | `dict` | `False / True` | No | Preserved column. Validation updated to support typed specifications contract. |
| *`is_available`* | `BooleanField` | *Physical DB column preserved during Phase 1/2* | `True` | `False / False` | **Yes** | Maintained for backward compatibility; synchronized via dual-write. |

### B. App: `apps.stores` — Model: `Store`

| Field Name | Type | Constraints | Default | Null / Blank | Index | Architectural Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `tagline` | `CharField` | `max_length=120` | `""` | `False / True` | No | Short marketing slogan displayed under store name on storefront header. |
| `whatsapp_number` | `CharField` | `max_length=20`, E.164 phone format | `""` | `False / True` | No | Optional storefront enquiry number. |
| `allow_whatsapp_fallback` | `BooleanField` | Standard boolean | `True` | `False / False` | No | If True, permits falling back to `Merchant.contact_number` when `whatsapp_number` is blank. |
| `social_links` | `JSONField` | Structured JSON dict with HTTPS validation | `dict` | `False / True` | No | Links to merchant social profiles (Instagram, Facebook, etc.). |

### C. App: `apps.products` — Model: `Category`
*Verification finding:* `display_order = models.PositiveIntegerField(default=0, db_index=True)` already exists in `apps/products/models.py`. **NO database schema migration is required for Category.**

---

## 7. Migration and Backward-Compatibility Plan

Database migrations must follow a phased lifecycle grounded in real database behavior:

### Migration Ordering & Safe Execution Sequence (Task 013)
1. **Schema Migration (`apps.products`):**
   - In PostgreSQL 11+, adding `availability_mode` with default `'IN_STOCK'`, `price_display_mode` with default `'SHOW_PRICE'`, and nullable `mrp` are **metadata-only updates** (no full table rewrite).
   - Add database `CheckConstraint`s:
     - `chk_prod_avail_mode_sync` (ensuring `availability_mode` and `is_available` remain coherent).
     - `chk_prod_price_mode_valid` (`price_display_mode IN ('SHOW_PRICE', 'CONTACT_FOR_PRICE')`).
     - `chk_prod_price_non_neg` (`price IS NULL OR price >= 0`).
     - `chk_prod_mrp_non_neg` (`mrp IS NULL OR mrp >= 0`).
     - `chk_prod_mrp_gte_price` (`mrp IS NULL OR price IS NULL OR mrp >= price`).
     - `chk_prod_pub_price` (`status != 'PUBLISHED' OR price_display_mode != 'SHOW_PRICE' OR price IS NOT NULL`).
   - Add consolidated compound index `idx_prod_mcht_mode_created` on `("merchant", "status", "availability_mode", "created_at")`.
2. **Data Migration (`apps.products`):**
   - Executes inside `migrations.RunPython`:
     - If `is_available == False`: set `availability_mode = 'OUT_OF_STOCK'`.
     - If `is_available == True`: set `availability_mode = 'IN_STOCK'`.
     - If `price is None` and `status == 'PUBLISHED'`: set `price_display_mode = 'CONTACT_FOR_PRICE'`.
     - If `price is not None`: set `price_display_mode = 'SHOW_PRICE'`.
     - If `price is None` and `status == 'DRAFT'`: set `price_display_mode = 'SHOW_PRICE'`.
   - **Rollback (`reverse_code`):** Backfills `is_available = (availability_mode != 'OUT_OF_STOCK')` to ensure clean downward rollbacks.
3. **Schema Migration (`apps.stores`):**
   - Add `tagline`, `whatsapp_number`, `allow_whatsapp_fallback`, `social_links` with safe defaults (`""`, `True`, `{}`).
4. **Dual-Write Synchronization in `services.py` & `models.py`:**
   - Both `create_product()` and `update_product_profile()` and `Product.save()` enforce dual-write synchronization.

---

## 8. Public Storefront URL, View, and Template Architecture

The public storefront is the primary consumer surface. It is strictly unauthenticated, read-only, and optimized for mobile devices.

### URL Structure
```
/s/<store_slug>/                      --> Public Storefront Home (Hero, Categories, Featured Products)
/s/<store_slug>/products/             --> Public Catalogue Browsing (Search, Category Filter Tabs)
/s/<store_slug>/products/?category=.. --> Filtered Catalogue by Category Slug
/s/<store_slug>/p/<product_slug>/     --> Public Product Detail Page (Gallery, Specs, WhatsApp CTA)
/s/<store_slug>/qr/                   --> Dynamic In-Memory Storefront QR Code Image (PNG)
```

### View & Selector Topology
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PUBLIC STOREFRONT ROUTING ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ URL: /s/<store_slug>/                                                       │
│ App: apps.stores                                                            │
│ View: PublicStorefrontHomeView (views_public.py)                            │
│ Selectors: get_public_store_by_slug(store_slug)                             │
│            get_public_storefront_categories(merchant)                       │
│            get_featured_storefront_products(merchant, limit=8)              │
│ Template: templates/stores/public_home.html                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ URL: /s/<store_slug>/products/                                              │
│ App: apps.products                                                          │
│ View: PublicProductListView (views_public.py)                               │
│ Selectors: get_public_storefront_products(merchant, category_slug, search)  │
│ Template: templates/products/public_list.html                               │
│ Partials: templates/products/partials/public_product_grid.html (HTMX)       │
├─────────────────────────────────────────────────────────────────────────────┤
│ URL: /s/<store_slug>/p/<product_slug>/                                      │
│ App: apps.products                                                          │
│ View: PublicProductDetailView (views_public.py)                             │
│ Selector: get_public_product_detail(merchant, product_slug)                 │
│ Template: templates/products/public_detail.html                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ URL: /s/<store_slug>/qr/                                                    │
│ App: apps.stores                                                            │
│ View: PublicStorefrontQRView (views_public.py)                              │
│ Output: Streaming HttpResponse(image/png) with 1hr Cache-Control             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Public Storefront Security & Visibility Invariants
Every incoming storefront request must satisfy the following invariant chain:
1. `Store` with matching `slug` exists $\rightarrow$ else `Http404`.
2. `Store.status == StoreStatus.PUBLISHED` $\rightarrow$ else `Http404`.
3. Associated `Merchant.status == MerchantStatus.ACTIVE` $\rightarrow$ else `Http404`.
4. For product detail views: `Product.status == ProductStatus.PUBLISHED` and belongs to this `merchant` $\rightarrow$ else `Http404`.
5. Products with `availability_mode == OUT_OF_STOCK` **remain visible** with an "Out of Stock" badge and enquiry prompt. They are never hidden.
6. Draft or Archived products return `Http404` unconditionally.
7. Public QR endpoint `/s/<store_slug>/qr/` strictly returns `Http404` if the store is not published or the merchant is not active.

---

## 9. Dashboard & Tenant-Isolation Security Rules

MyCatalogue enforces rigid multi-tenant boundary isolation:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECURITY & TENANT ISOLATION RULES                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Active Tenant Context:                                                   │
│    - Dashboard views resolve tenant via `request.merchant` (TenantMiddleware│
│    - Never trust client-supplied `merchant_id` in GET, POST, or URLs.       │
│                                                                             │
│ 2. Scoped Object Resolution:                                                │
│    - All ORM queries filter by `merchant=request.merchant`.                 │
│    - Example: `Product.objects.filter(merchant=request.merchant, pk=pk)`    │
│    - Un-scoped lookups by raw PK are strictly prohibited.                   │
│                                                                             │
│ 3. RBAC Permissions:                                                        │
│    - Dashboard catalogue operations require `MANAGE_CATALOGUE` permission.  │
│    - Permitted: OWNER, ADMIN, MANAGER. Denied: STAFF, GUEST.                │
│                                                                             │
│ 4. Cross-Tenant Integrity Guard:                                            │
│    - Category assignment verifies that all Category UUIDs belong to         │
│      `request.merchant`. Mismatches abort atomically with `PermissionDenied`│
│                                                                             │
│ 5. Storefront Isolation:                                                    │
│    - Storefront views (`/s/`) are unauthenticated and strictly READ-ONLY.   │
│    - Storefront views cannot mutate state or leak dashboard session info.   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Performance, Query Budgets & Authoritative Index Inventory

### Authoritative Final Database Index Inventory

```python
# apps/products/models.py — Product
class Product(BaseModel):
    class Meta:
        indexes = [
            # Consolidated query-justified index covering:
            # 1. Storefront catalog browsing (merchant, status, created_at)
            # 2. Filtered catalog browsing (merchant, status, availability_mode, created_at)
            # 3. Merchant dashboard list filtering
            models.Index(
                fields=["merchant", "status", "availability_mode", "created_at"],
                name="idx_prod_mcht_mode_created",
            ),
            # Existing legacy index preserved during Phase 1/2 transition:
            models.Index(
                fields=["merchant", "status", "is_available"],
                name="idx_prod_mcht_stat_avail",
            ),
        ]
        # Uniqueness constraints automatically index (merchant, lower(slug)) and (merchant, sku).
        # Standalone indexes on availability_mode and price_display_mode are intentionally omitted.

# apps/products/models.py — Category
# ALREADY EXISTS IN CODEBASE:
# models.Index(fields=["merchant", "is_active", "display_order"], name="idx_cat_mcht_active_order")

# apps/stores/models.py — Store
# ALREADY EXISTS IN CODEBASE:
# UniqueConstraint(Lower("slug"), name="unique_lowercase_store_slug") (provides unique B-tree index)
```

### Realistic Query Budgets vs Defensive Test Thresholds
To ensure the test suite verifies N+1 prevention without being unnecessarily brittle:

| Surface / Route | Expected Exact Query Count | Maximum Allowed Test Budget | Query Breakdown |
| :--- | :---: | :---: | :--- |
| **Storefront Home** (`/s/<slug>/`) | **4 queries** | **$\le 5$ queries** | 1: Store & Merchant (`select_related`)<br>2: Categories (`order_by`)<br>3: Featured Products (`slice 8`)<br>4: Prefetched Images<br>*(Budget allows 1 optional middleware query)* |
| **Storefront Catalogue** (`/s/<slug>/products/`) | **5 queries** | **$\le 6$ queries** | 1: Store & Merchant (`select_related`)<br>2: Categories for filter tabs<br>3: Total Count for Pagination<br>4: Paginated Products (`slice 12`)<br>5: Prefetched Images<br>*(Budget allows 1 optional middleware query)* |
| **Product Detail** (`/s/<slug>/p/<slug>/`) | **3 queries** | **$\le 4$ queries** | 1: Store & Merchant<br>2: Product & Categories (`prefetch_related`)<br>3: Product Images (`order_by`) |

- **Mandatory Pagination:** Storefront catalogue listing is strictly paginated (default **12 products per page**).
- **Automated Enforcement:** Test suite implements `assertNumQueries(budget)` or `CaptureQueriesContext` asserting queries remain within maximum budget.

---

## 11. Deferred Features & Future Roadmap

To preserve development velocity and avoid premature complexity, the following capabilities are explicitly classified into future milestones:

### Milestone 2: Operational Improvements (Post-MVP)
- **Printable A4 QR Merchandising Poster:** HTML/CSS `@media print` template generator allowing merchants to produce branded counter display posters with slogans and logos.
- **Faceted Storefront Attribute Search:** PostgreSQL GIN indexes on `Product.attributes` allowing shoppers to filter catalogue by color swatches and sizes.
- **CSV Bulk Product Import/Export:** Ingestion wizard in `/merchants/products/import/` with transactional rollback safety.
- **Bulk Inventory Inline Quick-Edit:** HTMX-powered spreadsheet table for rapid price and stock adjustment.
- **Image Cropper & Aspect Ratio Tool:** Client-side canvas cropping (1:1, 4:5 ratios) before upload.
- **Physical Column Removal:** Dropping deprecated column `is_available` from the database.

### Milestone 3: Growth & Advanced Platform (Future)
- **Async Telemetry Pipeline:** Low-latency event streaming (Redis buffer $\rightarrow$ roll-up tables) for visitor counts, page views, and WhatsApp clicks.
- **WhatsApp Cloud API Integration:** Automated bi-directional inventory stock alerts and customer broadcast messages.
- **Shopper Wishlists:** LocalStorage or cookie-backed saved products collection.
- **Multi-Branch Inventory Routing:** Geolocation-based routing to nearest physical branch.
- **Subscription Tier Quotas:** Automated plan enforcement (e.g., Free: 25 items; Pro: Unlimited).

---

## 12. Phased Implementation Task Sequence (Task 013 to Task 021)

Implementation is partitioned into nine strictly sequenced, dependency-controlled tasks. Artificial dependencies have been eliminated (Task 019 and Task 018 run independently off Task 013):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASED IMPLEMENTATION TASK SEQUENCE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Task 013: Domain Model Evolution & Migration                                │
│           (Availability Mode, Pricing Mode, Store Fields, Attribute Contract│
│           ┌────────────────────────┬────────────────────────┐               │
│           │                        │                        │               │
│           ▼                        ▼                        ▼               │
│ Task 014: Public Storefront   Task 018: Merchant      Task 019: Merchant    │
│           Foundation & URLs             Dashboard               Product Form│
│           │                             KPI Enhancement         UI Upgrades │
│           ├────────────────────────┐                                        │
│           ▼                        ▼                                        │
│ Task 015: Public Product      Task 020: Dynamic                             │
│           Catalogue Listing             Storefront QR                       │
│           │                             Endpoint                            │
│           ▼                                                                 │
│ Task 016: Public Product                                                    │
│           Detail & Gallery                                                  │
│           │                                                                 │
│           ▼                                                                 │
│ Task 017: WhatsApp Enquiry                                                  │
│           Conversion Flow                                                   │
│           │                                                                 │
│           └────────────────────────┬────────────────────────┘               │
│                                    ▼                                        │
│ Task 021: End-to-End Verification & Alignment Audit                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Task 013: Domain Model Evolution & Migration
- **Objective:** Implement data model enhancements approved in Decisions 1, 2, and 5 (Availability 3-state, Dual Pricing with `PriceDisplayMode`, Store fields including `allow_whatsapp_fallback`, Attribute JSON validation).
- **Dependencies:** Task 012 Approval.
- **Files Modified/Created:**
  - `apps/products/models.py`
  - `apps/products/choices.py`
  - `apps/products/validators.py`
  - `apps/products/services.py`
  - `apps/stores/models.py`
  - `apps/products/migrations/0002_*.py`
  - `apps/stores/migrations/0002_*.py`
- **Testing Requirements:**
  - Choice tests for `AvailabilityMode` and `PriceDisplayMode`.
  - Dual-write synchronization tests verifying both `availability_mode` and `is_available` remain in sync across all `update_fields` and instance mutations.
  - Multi-tier pricing validation tests (asserting `mrp >= price`, non-negative constraints, and draft vs published rules).
  - Custom attribute validator tests (validating typed specs, membership in options, boolean rejection in numbers, rejecting malformed hex, testing legacy coercion).
  - Migration rollback and forward test.
- **Exit Criteria:** Clean migrations; dual-write active; zero test regressions across existing 33 call sites.

---

### Task 014: Public Storefront Foundation & Routing
- **Objective:** Establish the public `/s/<store_slug>/` routing foundation, storefront base templates, and store homepage.
- **Dependencies:** Task 013.
- **Files Modified/Created:**
  - `apps/stores/urls.py`
  - `apps/stores/views_public.py`
  - `apps/stores/selectors.py`
  - `templates/stores/base_storefront.html`
  - `templates/stores/public_home.html`
- **Testing Requirements:**
  - HTTP 200 for `PUBLISHED` store with `ACTIVE` merchant.
  - HTTP 404 for `DRAFT` or `ARCHIVED` store.
  - HTTP 404 for suspended merchant.
  - Query budget assertion: Store Home renders in $\le 5$ SQL queries.
  - Verified rendering of existing `logo`, `cover_image`, and proposed `tagline`.
- **Exit Criteria:** Mobile-first storefront shell renders cleanly at `/s/<store_slug>/`.

---

### Task 015: Public Product Listing & Category Navigation
- **Objective:** Implement catalogue browsing, category filter tabs, search input, and HTMX pagination.
- **Dependencies:** Task 014.
- **Files Modified/Created:**
  - `apps/products/views_public.py`
  - `apps/products/selectors.py`
  - `templates/products/public_list.html`
  - `templates/products/partials/public_product_grid.html`
  - `templates/products/partials/public_product_card.html`
- **Testing Requirements:**
  - Category filtering query isolation using existing `Category.display_order`.
  - Query budget verification: catalogue listing executes in $\le 6$ SQL queries.
  - Out of stock items remain visible with badge.
  - Draft and archived items return 404.
  - HTMX pagination partial rendering.
- **Exit Criteria:** Visitors can browse, filter by category tabs, and search products with bounded query budgets.

---

### Task 016: Public Product Detail & Image Gallery
- **Objective:** Implement comprehensive product detail view with multi-image gallery carousel, dual pricing display, specifications table, and color swatches.
- **Dependencies:** Task 015.
- **Files Modified/Created:**
  - `apps/products/views_public.py`
  - `templates/products/public_detail.html`
  - `templates/products/partials/specifications_table.html`
- **Testing Requirements:**
  - Detail view test verifying draft product slug returns HTTP 404.
  - Price rendering test: Strikethrough + discount badge when `SHOW_PRICE` and `mrp > price`.
  - Price rendering test: "Contact for Price" badge when `CONTACT_FOR_PRICE`.
  - Specification rendering test: Color swatches, multi-select badges, and measurement units.
  - Query budget test: Detail page executes in $\le 4$ SQL queries.
- **Exit Criteria:** High-fidelity product detail view matching Stitch mobile design with responsive gallery viewer.

---

### Task 017: WhatsApp Enquiry Conversion Flow
- **Objective:** Implement contextual 1-click WhatsApp enquiry buttons on product cards and product detail pages with explicit fallback toggle logic.
- **Dependencies:** Task 016.
- **Files Modified/Created:**
  - `apps/products/templatetags/storefront_tags.py`
  - `apps/stores/services.py`
  - `templates/products/partials/whatsapp_cta.html`
  - `templates/products/public_detail.html`
- **Testing Requirements:**
  - URL builder test asserting properly URL-encoded WhatsApp deep links (`https://wa.me/<number>?text=<message>`).
  - Fallback test: uses `Store.whatsapp_number` if present; if blank and `allow_whatsapp_fallback` is True, falls back to `Merchant.contact_number`; if False or no number, suppresses gracefully.
  - Context test: pre-filled text includes Store Name, Product Title, SKU, Price, and Product URL.
- **Exit Criteria:** Shoppers clicking "Enquire on WhatsApp" are seamlessly directed to WhatsApp with pre-filled context.

---

### Task 018: Merchant Overview Dashboard Enhancement
- **Objective:** Upgrade the authenticated merchant overview dashboard (`/merchants/`) with real catalogue inventory metrics and storefront preview controls.
- **Dependencies:** Task 013.
- **Files Modified/Created:**
  - `apps/merchants/views.py`
  - `apps/merchants/selectors.py`
  - `templates/merchants/dashboard.html`
  - `templates/merchants/partials/catalogue_kpi_cards.html`
- **Testing Requirements:**
  - Permission test verifying `MANAGE_CATALOGUE` requirement.
  - Tenant isolation test: metrics accurately count only the active merchant's data.
  - Assertion that zero fake or simulated numbers are rendered.
  - Direct preview link to live public storefront.
- **Exit Criteria:** Dashboard displays accurate inventory KPIs and neutral "Analytics Coming Soon" notice.

---

### Task 019: Merchant Product Form Upgrades (Back-Office UI)
- **Objective:** Upgrade the back-office product create/edit form to support Dual Pricing (`price`, `mrp`, `price_display_mode`), Availability Mode dropdown, and the Merchant Attribute Form Builder UI.
- **Dependencies:** Task 013 (Independent of Task 018).
- **Files Modified/Created:**
  - `apps/products/forms.py`
  - `apps/products/views.py`
  - `templates/products/form.html`
  - `templates/products/partials/attribute_builder.html`
- **Testing Requirements:**
  - Form validation: rejects `price < 0`, enforces `mrp >= price` when provided.
  - Form validation: requires `price` when `SHOW_PRICE` and publishing.
  - Dynamic attribute builder tests: adding/removing typed specifications adhering to schema.
  - Service tests asserting save with all new fields.
- **Exit Criteria:** Merchants can manage dual pricing, availability, and structured attributes in the back-office dashboard.

---

### Task 020: Dynamic Storefront QR Code Endpoint
- **Objective:** Implement in-memory dynamic QR code generator endpoint with HTTP caching headers and public visibility controls.
- **Dependencies:** Task 014.
- **Files Modified/Created:**
  - `requirements.txt` (`qrcode>=8.0`)
  - `apps/stores/views_public.py`
  - `apps/stores/urls.py`
  - `templates/merchants/store/qr_preview.html`
- **Testing Requirements:**
  - Binary streaming test: `/s/<store_slug>/qr/` returns valid PNG binary (`image/png`).
  - Visibility test: returns HTTP 404 if store is DRAFT or ARCHIVED.
  - Back-office preview test: authenticated merchant can preview QR code even if DRAFT.
  - Cache header test: `Cache-Control: public, max-age=3600, stale-while-revalidate=300`.
  - Payload test: QR code encodes the canonical absolute URL of the storefront.
- **Exit Criteria:** High-resolution QR code streams on-demand without writing to disk or media storage.

---

### Task 021: End-to-End Verification & Design Alignment Audit
- **Objective:** Comprehensive automated test execution, cross-device browser verification, tenant security audit, and final project documentation.
- **Dependencies:** Tasks 013 through 020.
- **Files Modified/Created:**
  - `tests/e2e/test_storefront_journey.py`
  - `docs/architecture/TASK_021_COMPLETION_REPORT.md`
- **Testing Requirements:**
  - 100% test pass rate across entire suite (`pytest` / `python manage.py test`).
  - Query budget tests verifying storefront pages adhere to max defensive budgets.
  - Linting and format checks clean (`ruff check .`, `ruff format --check .`).
  - Cross-device visual verification (mobile, tablet, desktop).
  - Security audit confirming tenant boundary isolation.
- **Exit Criteria:** All tests green, linting clean, visual fidelity approved, human developer sign-off.

---

## 13. Open Decisions Requiring Human Decisions

The following architectural choices require explicit human developer approval:

### Question 1: Product Discount Display Format
* **Option 1 (Recommended):** Display percentage badge (e.g., `"25% OFF"`) on product cards; display dual badge (`"25% OFF (Save ₹500)"`) on the product detail page hero.
* **Option 2:** Display percentage only (`"25% OFF"`).
* **Option 3:** Display absolute savings amount only (`"Save ₹500"`).
* **Trade-off:** Option 1 maximizes mobile card density while providing full value transparency on the detail page.

### Question 2: Public Catalogue Pagination vs Infinite Scroll
* **Option 1 (Recommended):** HTMX-driven "Load More Products" button.
* **Option 2:** Automatic scroll-triggered infinite scroll (`hx-trigger="revealed"`).
* **Option 3:** Classic numeric page links (`« 1 2 3 »`).
* **Trade-off:** Option 1 avoids mobile scroll-trapping, enabling shoppers to easily reach the storefront footer, address, and social links.

---

## 14. Final Recommendation & Next Immediate Action

### Architecture Status: VERIFIED, RECONCILED & READY FOR HUMAN APPROVAL
All issues raised across all revisions have been definitively solved:
- Deterministic write-path synchronization specified with instance tracking and database `CheckConstraint` guard.
- Multi-tier pricing validation clarified with explicit publishing requirements.
- Store model and WhatsApp fallback reconciled with `allow_whatsapp_fallback` boolean.
- QR caching and revocation documented truthfully.
- Single query-justified compound index inventory established.
- Complete typed attribute and social link validation contract specified.
- Realistic query budgets and defensive test thresholds defined.

### Next Immediate Action:
Await human developer authorization on Revision 3 and answers to the Open Decisions in Section 13.

**STRICT COMPLIANCE CONFIRMATION: Zero application code, models, migrations, templates, or settings were modified in this task.**
