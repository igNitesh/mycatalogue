# Frontend Engineering Standards --- MyCatalogue

> Purpose: Build a polished, responsive, consistent merchant SaaS
> interface. The frontend must feel deliberate and production-ready on
> desktop, tablet, and mobile. Avoid oversized elements, awkward
> spacing, broken layouts, and desktop-only designs.

## 1. Project context and technology constraints

MyCatalogue is a Django modular-monolith SaaS for independent merchants.

Use the existing stack: - Django Templates for server-rendered pages. -
Tailwind CSS using the project's existing build and configuration. -
HTMX for progressive interactions where useful. - Small amounts of
vanilla JavaScript only when necessary. - Existing Django forms,
authentication, sessions, URLs, and permission services.

Do not introduce React, Vue, Bootstrap, a second CSS framework, a
component library, or a new JavaScript build system without explicit
approval. Do not duplicate existing styling systems.

Before changing frontend code, inspect: - `templates/base.html` and
existing template inheritance. - Tailwind configuration and CSS entry
points. - Existing reusable form, button, alert, badge, and navigation
styles. - Existing HTMX setup and CSRF handling. - Current URL names and
view context. - Existing app-specific templates.

Reuse established patterns when they are sound. Do not perform broad
redesigns of unrelated pages.

## 2. Core visual principles

### 2.1 Responsive by default

Every page must work at narrow mobile widths first, then scale up.
Desktop is not the only target.

Minimum viewport checks: - 320px: narrow mobile. - 375px: common
mobile. - 430px: large mobile. - 768px: tablet. - 1024px: small
laptop. - 1280px: desktop. - 1440px: wide desktop.

No horizontal page scrolling at these widths unless a specific data
table intentionally uses a contained horizontal scroll region.

### 2.2 Avoid oversized UI

Do not make everything large to create visual impact.

Use restrained dimensions: - Standard body text: 14--16px. - Supporting
text: 12--14px. - Page title: usually 24--32px desktop and 22--28px
mobile. - Section heading: usually 18--22px. - Card padding: usually
16--24px. - Standard button height: around 36--44px. - Input height:
around 40--44px. - Icon size: usually 16--20px for controls and 20--24px
for prominent navigation. - Sidebar width: usually 220--260px on
desktop. - Header height: usually 56--68px. - Content max width: choose
a sensible limit (often 1200--1400px) rather than stretching text across
an ultra-wide screen.

These are starting points, not rigid laws. Follow the existing design
system where one exists. Make icons, controls, and typography
proportional to their purpose.

Avoid: - Huge hamburger icons or oversized menu bars. - Giant headings
that push useful content below the fold. - Excessive empty space. - Very
tall cards with little content. - Buttons that are much larger than
their importance. - Full-width controls when a compact control is
clearer. - Excessively rounded cards, pills, and buttons everywhere. -
Decorative gradients, shadows, and borders without a clear purpose.

### 2.3 Clear hierarchy

Each page should have: 1. One clear page title. 2. A short description
only when it adds context. 3. A clear primary action, if one exists. 4.
Grouped content with consistent section headings. 5. Supporting
information visually subordinate to primary content.

Do not give every element equal visual weight. Use size, weight,
spacing, and contrast consistently.

### 2.4 Consistent spacing

Use a deliberate spacing scale. Prefer Tailwind's existing spacing
tokens rather than arbitrary values.

Suggested rhythm: - 4px: tiny icon/text separation. - 8px: compact
internal gap. - 12px: related controls. - 16px: standard component
spacing. - 24px: card or section spacing. - 32px: major section
separation. - 48px: large page-level separation.

Avoid random combinations such as `mt-7`, `p-11`, `gap-13` unless the
design genuinely needs them. Keep related elements close and separate
unrelated groups.

## 3. Responsive layout requirements

### 3.1 Layout behaviour

-   Use mobile-first Tailwind classes.
-   Use CSS Grid and Flexbox for layout.
-   Use `min-w-0` where flex/grid children could overflow.
-   Use `w-full` only when the element should truly occupy the available
    width.
-   Use `max-w-*` to prevent forms and text from becoming excessively
    wide.
-   Allow columns to stack on mobile.
-   Keep page content inside a consistent responsive container.
-   Use responsive padding, for example `px-4 sm:px-6 lg:px-8`.
-   Avoid fixed widths for main content areas.
-   Avoid fixed heights for content cards and sections unless required
    for a specific UI pattern.

### 3.2 Dashboard shell

For merchant dashboard pages: - Desktop: fixed or sticky sidebar with a
clear content region. - Tablet: compact or collapsible sidebar as
appropriate. - Mobile: sidebar hidden by default and opened with a
compact menu button. - The mobile drawer must have an accessible close
action. - The page must not be obscured by an open drawer without a
clear way to close it. - Header content must wrap or collapse
gracefully. - Merchant name, status, switcher, and account controls must
not collide. - The content region must use `min-w-0` and avoid causing
viewport overflow.

Do not render an oversized hamburger icon. Use a consistent 20--24px
icon with a reasonable clickable target (at least 44px where practical).
The clickable area may be larger than the visible icon.

### 3.3 Forms

-   Use a single column on narrow screens.
-   Use two columns only when fields are logically related and there is
    sufficient width.
-   Labels must remain visible; do not rely on placeholders as labels.
-   Inputs must fit their containers.
-   Validation messages must wrap and remain near the relevant field.
-   Submit buttons must remain reachable and must not overflow.
-   Do not place long forms in excessively wide containers.

### 3.4 Tables and dense data

-   Do not force wide tables to shrink until text becomes unreadable.
-   Use a contained horizontal scroll region for genuinely wide tables.
-   Keep page-level overflow hidden only when the table itself provides
    an accessible scroll area.
-   On mobile, consider a stacked card presentation if it improves
    usability and is reasonable for the data.
-   Preserve clear column labels and meaningful row actions.

## 4. Typography

-   Use the project's existing font stack unless there is an approved
    design decision to change it.
-   Use a consistent type scale and font weights.
-   Body text should be comfortable to read, not tiny.
-   Use line-height appropriate to the text size.
-   Keep paragraphs at a readable line length.
-   Avoid all-caps for long labels and headings.
-   Use muted text for secondary information, but maintain accessible
    contrast.
-   Do not use bold text for every label.
-   Prevent headings from overflowing: allow wrapping and use sensible
    max widths.

## 5. Colour, borders, and elevation

-   Follow one coherent palette across the product.
-   Use semantic colours consistently:
    -   Success: active, completed, published.
    -   Warning: pending, needs attention.
    -   Danger: destructive action, suspended, errors.
    -   Neutral: drafts, inactive information, secondary UI.
-   Do not rely on colour alone to communicate status; include text.
-   Use subtle borders to separate regions.
-   Use shadows sparingly and consistently.
-   Avoid adding a different colour treatment to every card.
-   Keep disabled states visibly disabled, but readable.
-   Ensure text/background contrast is sufficient.

Do not invent a new palette on every page. Inspect and reuse the
project's current design tokens.

## 6. Components and interaction states

Create or reuse consistent patterns for: - Primary, secondary, and
destructive buttons. - Text inputs, selects, checkboxes, and
textareas. - Form labels and validation errors. - Status badges. -
Alerts and notices. - Cards and empty states. - Dropdowns and menus. -
Sidebar navigation. - Confirmation prompts for destructive actions.

Every interactive component must account for: - Default state. - Hover
state. - Keyboard focus state. - Active/pressed state. - Disabled
state. - Loading state, where relevant. - Error or success feedback,
where relevant.

Do not make non-functional elements look clickable. Do not use fake
links (`href="#"`) for disabled navigation. Use semantic disabled
controls or non-interactive text with a clear "Coming soon" label.

## 7. Accessibility

-   Use semantic HTML: `header`, `nav`, `main`, `aside`, `section`,
    `form`, and appropriate headings.
-   Maintain a logical heading hierarchy.
-   All form controls need associated labels.
-   All interactive controls must be keyboard accessible.
-   Provide visible focus styles; never remove outlines without
    replacement.
-   Use buttons for actions and links for navigation.
-   Icon-only buttons need an accessible name (`aria-label`).
-   Mobile drawer controls must expose expanded state and appropriate
    relationships.
-   Use `aria-current="page"` for active navigation where appropriate.
-   Use `aria-live` for important asynchronous feedback when suitable.
-   Do not use colour as the only status signal.
-   Respect reduced-motion preferences.
-   Avoid unnecessary animation and motion.

## 8. Django template and HTMX practices

-   Keep business logic and permission checks in views/services, not
    templates.
-   Templates may display already-authorized context; they must not
    decide tenant access.
-   Use named Django URL patterns instead of hard-coded internal paths.
-   Escape user-provided content by default.
-   Do not mark user content as safe unless it has been safely
    sanitized.
-   Keep template conditionals readable; move complex logic into Python.
-   Preserve CSRF protection for all state-changing POST forms.
-   HTMX requests must respect authentication, permissions, CSRF, and
    tenant isolation.
-   Provide useful feedback after HTMX actions.
-   Ensure interactions still have a sensible fallback where practical.
-   Do not add JavaScript dependencies for interactions that can be
    handled cleanly with HTML, CSS, Django, or HTMX.

## 9. Performance and maintainability

-   Avoid unnecessary JavaScript.
-   Avoid loading multiple icon libraries.
-   Prefer the project's existing icon solution or small inline SVGs.
-   Avoid large images where small assets will do.
-   Set image dimensions or aspect ratios to reduce layout shifts.
-   Lazy-load below-the-fold images where appropriate.
-   Do not add CSS overrides to compensate for poorly structured markup.
-   Remove obsolete styles only when their usage has been checked.
-   Avoid `!important` unless there is a documented reason.
-   Do not duplicate large blocks of template markup; use includes or
    template inheritance when that improves clarity.
-   Keep responsive classes readable and consistent.

## 10. Visual QA is mandatory

Automated tests do not prove that a page looks good. Before marking a
frontend task complete:

1.  Run Django system checks and relevant automated tests.
2.  Run the project's CSS/Tailwind build.
3.  Open the actual page in a browser.
4.  Inspect at 375px, 768px, 1280px, and 1440px widths.
5.  Check for horizontal overflow.
6.  Check alignment, spacing, typography, and component proportions.
7.  Test menus, dropdowns, forms, and responsive navigation.
8.  Check empty, loading, error, disabled, and success states where
    applicable.
9.  Capture full-page screenshots at desktop and mobile widths.
10. Fix visual defects before reporting completion.

Do not claim responsive verification if only desktop was inspected. If
browser automation or a browser is unavailable, state that visual QA
remains unverified; do not pretend it was completed.

### Visual defect checklist

-   [ ] No horizontal page scrolling at supported widths.
-   [ ] No oversized icons, headings, buttons, or cards.
-   [ ] No overlapping header/sidebar/content.
-   [ ] No clipped text or controls.
-   [ ] No awkward empty gaps.
-   [ ] Consistent spacing and alignment.
-   [ ] Mobile navigation can open and close.
-   [ ] Forms are usable on narrow screens.
-   [ ] Focus indicators are visible.
-   [ ] Disabled controls cannot be activated.
-   [ ] Status text is readable and not colour-only.
-   [ ] Desktop and mobile screenshots reviewed.

## 11. AI coding agent workflow for frontend tasks

For every frontend task:

### Phase 1 --- Inspect

-   Inspect existing templates, CSS, Tailwind config, JavaScript, and
    relevant views.
-   Identify the exact cause of the issue before changing styles.
-   Check whether a shared component can solve the issue.
-   Do not modify files yet.

### Phase 2 --- Plan

Report: - Root cause. - Files to create or modify. - Proposed responsive
behaviour. - Components/styles to reuse. - Accessibility
considerations. - Browser viewports to verify.

Wait for approval if the task requires architecture changes, new
dependencies, broad redesign, or changes outside the approved scope.

### Phase 3 --- Implement

-   Make focused changes.
-   Preserve existing backend behaviour and URL contracts.
-   Do not weaken authentication, permissions, tenant isolation, or
    CSRF.
-   Do not introduce unrelated refactoring.

### Phase 4 --- Verify

-   Run automated tests and frontend build/checks.
-   Perform browser visual QA at mobile, tablet, and desktop widths.
-   Capture screenshots.
-   Report exact commands and results.
-   List any unverified behaviour honestly.

## 12. Definition of done

A frontend task is complete only when: - The requested functionality
works. - The design follows the existing MyCatalogue visual system. -
The page is responsive at mobile, tablet, and desktop widths. - No major
overflow, clipping, overlap, or oversized UI remains. - Accessibility
basics are covered. - Existing backend security and tenant boundaries
are preserved. - Automated tests and relevant builds pass. - Browser
visual QA has been performed or explicitly marked as outstanding. - The
agent provides a concise implementation report with files changed and
screenshots.

**Highest priority:** clarity, proportion, usability, consistency, and
responsiveness. Do not add visual complexity just to make a page look
more "designed."
