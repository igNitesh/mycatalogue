# Architecture Overview – mycatalogue SaaS

## 1. Architectural Style
`mycatalogue` is built as a **modular monolith** in Python using Django 5.x.
The architecture prioritizes:
- Simplicity and maintainability over premature microservice distribution.
- Strict merchant-level multi-tenant isolation.
- Domain-driven organization of Django applications inside `apps/`.
- Progressive enhancement with HTMX and Tailwind CSS (avoiding SPA complexity while preserving reactive UX).

## 2. Directory Layout & Boundaries
- `apps/`: Encapsulated domain business applications. Each application manages its own models, services, views, and unit tests.
- `config/`: Project orchestration, routing, and environment-based settings.
- `templates/`: Global base layouts and shared atomic UI partials.
- `static/`: Frontend assets (compiled CSS, vendored HTMX).
- `docker/`: Container definitions and entrypoint automation.

## 3. Multi-Tenancy Principles
- Every merchant-owned record must have an explicit relationship to a merchant/tenant entity.
- Ownership and permissions must always be enforced server-side.
- Client-provided identifiers are never trusted blindly.

## 4. Frontend Philosophy
- Server-rendered HTML via Django Templates.
- HTMX handles dynamic asynchronous updates, partial page replacements, and state transitions without client-side state fragmentation.
- Tailwind CSS compiled via the Tailwind CLI provides a consistent, mobile-first design system.
