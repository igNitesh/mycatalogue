# My Catalogue Product Overview

## Purpose

My Catalogue is a multi-tenant digital storefront platform for local Indian shops. It gives each merchant an organization-specific workspace and a public storefront for presenting the merchant's published catalogue.

The implemented platform is based on a Django modular monolith. It supports email-based user accounts, merchant organizations, role-based merchant memberships, storefront profiles, products, categories, product images, and public store browsing.

This overview describes functionality present in the repository as of commit `704ababa36ee12c5b9e53af9b1ff51acc35beea1`. It does not imply that unimplemented modules or UI placeholders are available.

## Who Uses the Product

### Merchants

A merchant is represented by a `Merchant` organization. Merchant users create or join organizations and select an active merchant context for dashboard operations.

Implemented merchant roles are:

- **Owner** — highest level of merchant administration, including ownership transfer and account lifecycle permissions.
- **Admin** — merchant management, including store and catalogue operations.
- **Manager** — operational storefront, staff, sales, and catalogue permissions.
- **Staff** — storefront operations only; catalogue management is not granted.

### Customers

Customers can browse public storefronts through `/s/<store-slug>/`. Public access is available only when the store is published and the associated merchant is active. Customer checkout, cart, ordering, and payment workflows are not implemented in the reviewed codebase.

### Platform Administrators

The Django administration site is available at `/admin/`. Broader product-level platform-administrator workflows are not documented because the repository does not provide a separate verified platform-administrator UI or role model.

## Core Capabilities

### Implemented

- Email and password registration.
- Email verification, login, logout, and password reset.
- Merchant creation and merchant onboarding.
- Active merchant context switching.
- Merchant memberships with Owner, Admin, Manager, and Staff roles.
- Ownership transfer and merchant lifecycle operations.
- Store profile creation and editing.
- Store slug validation and availability checks.
- Store publishing and unpublishing.
- Public store detail pages for active, published stores.
- Product creation, editing, listing, searching, filtering, publishing, unpublishing, and archiving.
- Category creation, editing, activation, and deactivation.
- Product-category assignment with cross-merchant assignment protection.
- Product image uploads and validation.
- Primary product image selection and image deletion.
- Public product visibility rules that require an active merchant, published store, and published product.
- Server-side tenant isolation for merchant-owned data.
- Automated tests for authentication, authorization, tenant isolation, store behavior, and catalogue behavior.

### Not Verified or Not Implemented

- Customer cart and checkout.
- Orders and order history.
- Payments or refunds.
- Inventory quantity tracking.
- Product variants.
- Merchant billing and subscriptions.
- Booking or appointment functionality.
- Separate production platform-administrator UI.
- Verified end-to-end browser or screenshot evidence.

Dashboard modules may appear disabled or marked “Soon.” Those placeholders must not be treated as implemented features.

## Main Domain Areas

| Domain | Responsibility |
|---|---|
| `users` | Custom email-based user model, authentication, verification, password reset, and login security |
| `merchants` | Merchant organizations, memberships, roles, permissions, onboarding, context switching, and lifecycle operations |
| `stores` | Store profiles, public URLs, store publication, and public storefront access |
| `products` | Products, categories, product-category relationships, custom attributes, product lifecycle, and image galleries |
| `core` | Project health checks and foundational public pages |

## Typical Merchant Workflow

1. Register for an account.
2. Verify the email address.
3. Sign in.
4. Create or select a merchant organization.
5. Complete merchant onboarding when required.
6. Create and configure the store profile.
7. Set the public store slug.
8. Add categories.
9. Add and edit products.
10. Upload product images and select a primary image.
11. Publish products and publish the store when it is ready.

Not every step is permitted at every merchant status or membership role. Catalogue management is available to Owners, Admins, and Managers, but not Staff.

## Typical Customer Workflow

1. Open a public store URL in the form `/s/<store-slug>/`.
2. The store is shown only if the store is published and the merchant is active.
3. The public storefront is intended to present the store profile and eligible published products.
4. Out-of-stock products remain visible with an availability indicator; `is_available=False` does not hide a published product.

The public store view currently renders store details. Public product-selection rules exist in the product domain, but the public product catalogue integration in `public_detail.html` requires UI verification before a complete browsing journey can be documented.

## Multi-Tenancy and Isolation

Merchant-owned data is scoped to the selected `Merchant` organization. The implementation uses:

- Explicit merchant foreign keys on merchant-owned models.
- Server-side membership and role checks.
- Active session-based merchant context.
- Merchant-scoped slug and SKU uniqueness.
- Merchant-scoped category and product queries.
- Protection against assigning products and categories from different merchants.
- Database constraints for key uniqueness and relationship integrity.

Tenant isolation is a security requirement and is covered by dedicated automated tests.

## Verification Summary

This overview is based on repository code, migrations, route definitions, templates, automated tests, and recent commit information.

Evidence supporting the implemented capabilities includes:

- Automated Django test modules under `apps/users/tests`, `apps/merchants/tests`, `apps/stores/tests`, and `apps/products/tests`.
- A successful CI workflow run on commit `704ababa36ee12c5b9e53af9b1ff51acc35beea1`.
- Explicit domain models and constraints in each application.
- Merchant permission and role definitions.
- Merchant-scoped selectors and services.
- Public-store and public-product visibility tests.

CI success proves that the recorded workflow concluded successfully; it does not replace browser, visual, or production verification. No screenshots or manual UI test report are included in the repository.

## Documentation Status

- Product overview: **Draft, code-verified**
- Feature catalogue: **Not yet created**
- Merchant guide: **Not yet created**
- Customer guide: **Partially known; requires UI verification**
- Administrator guide: **Not yet created**
- Technical documentation: **Existing architecture and development guides require audit**
- Screenshot coverage: **Not available**

## Source References

- [Repository README](../../README.md)
- [Engineering instructions](../../agent.md)
- [Architecture overview](../architecture/overview.md)
- [Merchant permissions](../../apps/merchants/permissions.py)
- [Merchant and membership models](../../apps/merchants/models.py)
- [Store model](../../apps/stores/models.py)
- [Store routes](../../apps/stores/urls.py)
- [Product models](../../apps/products/models.py)
- [Product services](../../apps/products/services.py)
- [Product routes](../../apps/products/urls.py)
