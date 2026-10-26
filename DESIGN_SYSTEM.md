# Pasion website visual refresh

This visual refresh is now retired at the user's request. `main.jsx` no longer
imports `design-system.scss`; the previous Pasion theme and original layouts
are active. The notes below describe the historical redesign, not the current
site. Calculation bindings now reuse original widgets; current gaps are listed
in `IMPLEMENTATION_ROADMAP.md` under “Existing-screen calculation integration”.

The shared system lives in `src/design-system.scss`, loaded after the existing
feature themes. It gives the public site, authentication, workspace, reviewed
research tools, portfolio, account settings and administration one visual
language while retaining their existing routes, data modes and interactions.

The palette uses a deep navy navigation surface, warm neutral page backgrounds,
teal actions and restrained semantic success/error colors. Local Inter fonts
provide workspace hierarchy; the public hero retains editorial serif type.
Panels, tables, numeric alignment, inputs, tabs, source details, empty states,
focus rings and disabled states share consistent treatment. Dark mode uses
separate surface/text tokens, and reduced-motion preferences are respected.

Detail fixes include a scrollable sidebar at short viewport heights, compact
mobile toolbar, aligned valuation controls, balanced six-method model grid,
responsive scenario fields, proper portfolio tabs and confirmation row,
non-stretched planner cards, styled watch/assistant/admin forms, corrected
separator text, and proper shortcut/clear/sidebar icons.

Visual evidence uses local Edge with a mocked review identity and the existing
local application. No production accounts or financial records were changed.
`scripts/design-review.mjs` captures the main desktop routes, public pages,
dark mode and mobile layout; it records page errors and mobile widths.
`scripts/design-details.mjs` additionally captures valuation, manual portfolio,
settings and admin screens. Initial captures exposed a legacy sidebar override
and portfolio mobile overflow; both were corrected. The subsequent portfolio
check measured a 390px document at a 390px viewport with no JavaScript errors.

The browser design tests passed keyboard-search/theme switching and navigation
through nine mobile research routes without page overflow. The initial combined
run stalled before its other three checks started; do not represent that whole
run as passing. Build validation succeeds; the pre-existing large JavaScript
bundle warning remains. Screenshots under `artifacts/design-*` are local review
evidence, not a claim of every possible data-populated/error/locale combination.

The separate three-check retry also timed out before starting its tests. The
sign-in/planner/portfolio interaction group is therefore not claimed as passing
for this revision. Independent screenshot checks did complete for public login,
desktop/mobile portfolio, valuation, settings and administration without page
exceptions. The final production build passed after the utility-form polish.
