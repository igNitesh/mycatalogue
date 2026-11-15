# ADR 0001: Project Foundation & Technology Selection

## Status
Accepted

## Context
We are architecting a multi-tenant Digital Storefront SaaS (`mycatalogue`). The platform requires high developer velocity, rock-solid security, tenant isolation, and low operational overhead.

## Decisions

1. **Modular Monolith over Microservices**:
   We will keep all core domain modules in a single repository and runtime. This simplifies transactions, local development, and deployments while maintaining clear internal boundaries.

2. **Django Templates + HTMX over Heavy SPA**:
   Instead of introducing React/Next.js and separating frontend from backend APIs, we use server-rendered Django templates with HTMX for reactive interactivity. This eliminates state-synchronization duplication, decreases bundle size, and improves security.

3. **PostgreSQL as Primary Database**:
   PostgreSQL provides JSONB, robust relational integrity, row-level security capabilities, and transaction guarantees required for commerce and merchant operations.

4. **12-Factor Settings Separation**:
   Settings are split into `base`, `development`, `staging`, `production`, and `test`, using `django-environ` to read runtime configuration from environment variables.

5. **Containerization with Docker Compose**:
   Standardized environment across development, CI, and deployment targets using multi-stage Docker builds.

## Consequences
- Fast initial development and low infrastructure cost.
- Easy on-boarding for developers.
- Clean foundation ready for future business domains (catalog, merchants, orders, analytics).

