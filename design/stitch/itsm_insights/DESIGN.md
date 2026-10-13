---
name: ITSM Insights
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#434655'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#006a61'
  on-secondary: '#ffffff'
  secondary-container: '#86f2e4'
  on-secondary-container: '#006f66'
  tertiary: '#784b00'
  on-tertiary: '#ffffff'
  tertiary-container: '#996100'
  on-tertiary-container: '#ffeedd'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#89f5e7'
  secondary-fixed-dim: '#6bd8cb'
  on-secondary-fixed: '#00201d'
  on-secondary-fixed-variant: '#005049'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 22px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.04em
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
  metric-val:
    fontFamily: JetBrains Mono
    fontSize: 28px
    fontWeight: '500'
    lineHeight: 32px
    letterSpacing: -0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

The design system establishes a high-precision, utilitarian aesthetic tailored for enterprise infrastructure monitoring, incident response teams, and IT leadership. The visual posture is analytical, composed, and deliberate. 

Key attributes:
- **Tone:** Methodical, reliable, authoritative, and quiet.
- **Visual Movement:** Contemporary Enterprise Minimalism coupled with data-dense clarity. Avoids gratuitous ornamentation, decorative shadows, or distracting gradients.
- **Experience Goals:** Minimize cognitive load during high-severity triage, surface critical SLA risks instantly, and deliver scannable, calm analytics over extended shifts.

## Colors

The palette balances a subdued structural foundation with semantically strict status indicators.

### Foundational Neutrals
- **Light Mode Canvas:** `#F8F9FA` forms the base page background. Card and panel surfaces elevate to `#FFFFFF` with precise 1px borders in `#E2E8F0`. Secondary neutral fills (table headers, filter bars) utilize `#F1F5F9`.
- **Dark Mode Canvas:** `#0D1117` provides deep structural framing. Elevated surfaces utilize `#161B22` with border definition in `#30363D`. Muted header fills employ `#21262D`.

### Primary & Secondary Accents
- **Primary Blue (`#2563EB`):** Applied strictly to interactive controls, key navigation anchors, focus rings, and primary action states. In dark mode, this softens to `#3B82F6` for accessibility against dark surfaces.
- **Secondary Teal (`#0D9488`):** Reserved for systemic metrics, telemetry series, and auxiliary automation flows.

### Functional Status Tokens
- **Success / Healthy (`#10B981`):** SLA targets met, nominal cluster status, resolved tickets. Subdued tint: `#ECFDF5` (light) / `rgba(16, 185, 129, 0.15)` (dark).
- **Warning / Degraded (`#F59E0B`):** Near-breach thresholds, resource warnings, queued state. Subdued tint: `#FFFBEB` (light) / `rgba(245, 158, 11, 0.15)` (dark).
- **Critical / SLA Breach (`#EF4444`):** Active breach, critical incident, system outage. Subdued tint: `#FEF2F2` (light) / `rgba(239, 68, 68, 0.15)` (dark).
- **Neutral Info (`#64748B`):** Inactive nodes, unassigned tasks, informational metadata.

## Typography

The type hierarchy prioritizes high information density and structural scanning.

- **Primary Stack:** Implemented via neutral system-first sans (`Inter`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `Roboto`, `sans-serif`) to ensure native rendering speed and zero layout shifts across desktop workstations.
- **Monospace Stack:** `JetBrains Mono` (or local fallback `"SF Mono"`, `"Fira Code"`, `Menlo`, `monospace`) governs telemetry readouts, IP configurations, payload previews, and numeric data cells.
- **Tabular Figures:** All numeric tables and data cells enforce `font-variant-numeric: tabular-nums` to ensure strict vertical column alignment across rapidly updating feeds.
- **Scale Usage:**
  - `metric-val` is reserved for KPI cards and threshold counts.
  - `label-sm` enforces uppercase treatment with expanded tracking (`0.04em`) for status headers and metadata tags.

## Layout & Spacing

Layouts adhere to an 8px rhythmic grid engineered for complex administrative interfaces.

### Grid Architecture
- **Desktop (1280px+):** 12-column layout with fixed 256px collapsible left navigation. Gutters: `1.5rem` (`24px`). Outer boundary margin: `2rem` (`32px`).
- **Tablet (768px - 1279px):** 8-column layout. Sidebar collapses to 64px icon dock. Gutters: `1rem` (`16px`). Canvas margins: `1.5rem` (`24px`).
- **Mobile (Below 768px):** 4-column single-stream stack. Sidebar moves to an off-canvas drawer. Outer margins: `1rem` (`16px`). Table regions shift to horizontally scrollable viewports with pinned identification columns.

### Density and Padding
- Internal card padding defaults to `space-lg` (`20px`) for high-level summaries and compresses to `space-md` (`12px`) for nested log collectors and configuration inspectors.
- Compact cell density is favored over expansive whitespace to maximize vertical monitor capacity during incident investigations.

## Elevation & Depth

Depth is established primarily through low-contrast structural boundaries and tonal contrast rather than high-blur shadows.

- **Borders over Shadows:** Surfaces utilize a strict 1px solid border (`#E2E8F0` in light, `#30363D` in dark) to anchor elements cleanly to the canvas.
- **Base Level (Canvas):** Tone `#F8F9FA` / `#0D1117`. Flat, static background.
- **Level 1 (Cards, Tables, Panels):** Pure solid fill (`#FFFFFF` / `#161B22`) bound by 1px stroke. No box-shadow during rest states.
- **Level 2 (Dropdowns, Popovers, Context Menus):** Surface fill matching Level 1 with crisp border and a micro shadow: `0 4px 12px rgba(0, 0, 0, 0.06)` (light mode) or `0 4px 16px rgba(0, 0, 0, 0.4)` (dark mode).
- **Level 3 (Modal Dialogs, Incident Drilldowns):** Floating centered panels accompanied by an ambient backdrop overlay (`rgba(15, 23, 42, 0.4)` in light mode, `rgba(0, 0, 0, 0.7)` in dark mode). Border-radius: 8px.

## Shapes

The design system employs a disciplined, soft shape radius (Token `1` / `4px` baseline) conveying structural precision and space efficiency.

- **Base Radius (4px / 0.25rem):** Form inputs, buttons, status chips, dropdown triggers, and monospaced code blocks.
- **Container Radius (8px / 0.5rem):** Primary cards, data tables, modal dialogs, and slide-out telemetry trays.
- **Status Indicators (Pill / 9999px):** Standalone status dots and binary availability pips. Status badge containers remain strictly soft-rectangular (`4px`) to preserve horizontal layout space.

## Components

### Buttons
- **Primary:** Background `#2563EB`, text `#FFFFFF`, border `transparent`. Hover: `#1D4ED8`. Focus: `2px solid #93C5FD` offset by 2px.
- **Secondary / Outline:** Background `#FFFFFF` (or `#161B22`), border `1px solid #CBD5E1` (`#30363D`), text `#334155` (`#E2E8F0`). Hover: `#F8F9FA` (`#21262D`).
- **Destructive:** Background `#EF4444`, text `#FFFFFF`. Hover: `#DC2626`.
- **Dimensions:** Height 32px (compact) or 36px (default). Monospace is not used on action buttons; standard medium-weight sans applies.

### Status Badges & Chips
- Non-interactive indicators displaying incident severity, team assignments, or health flags.
- **Visual Structure:** Flat 1px outline paired with a 10% opacity tint of the respective status color.
  - *Healthy:* Text `#059669`, background `#ECFDF5`, border `#A7F3D0`.
  - *Warning:* Text `#D97706`, background `#FFFBEB`, border `#FDE68A`.
  - *Breach:* Text `#DC2626`, background `#FEF2F2`, border `#FECACA`.
- Includes a leading 6px circle with a solid status fill.

### Data Tables
- **Header Row:** Height 36px, background `#F8F9FA` (`#161B22`), border-bottom `1px solid #E2E8F0` (`#30363D`). Font: `label-sm` (uppercase, letter-spaced, text `#64748B`).
- **Data Rows:** Height 40px (standard) or 32px (condensed). Alternating row striping is omitted; separation relies on horizontal rules (`#F1F5F9` / `#21262D`).
- **Row Interaction:** Hover state activates `#F8FAFC` (`#1C2128`) background transition.
- **Alignment:** Metrics, dates, durations, and counts right-aligned using tabular monospace typography (`code-md` / `code-sm`).

### Form Inputs & Filters
- **Text Inputs & Dropdowns:** 32px or 36px height, 1px border (`#CBD5E1` / `#30363D`), background `#FFFFFF` (`#0D1117`). Placeholder text `#94A3B8`.
- **Active / Focus:** Border shifts to `#2563EB` with a `0 0 0 1px #2563EB` box-shadow. No fuzzy glow.
- **Checkboxes & Radios:** 14px size, 3px border-radius for checkboxes, fully circular for radios. Checked state: `#2563EB` fill with white checkmark icon.

### Cards & Panels
- Constructed with `#FFFFFF` (`#161B22`) background and `1px solid #E2E8F0` (`#30363D`).
- Separated into three distinct horizontal zones:
  - **Header:** 44px height, integrated border-bottom, flex alignment containing metric title, count pill, and contextual options menu.
  - **Body:** Dynamic content area utilizing standard padding (`space-md` or `space-lg`).
  - **Footer:** Optional light grey utility bar (`#F8F9FA` / `#161B22`) for pagination or timestamps.

### Monospace Code / YAML Viewer
- Embedded blocks for alert payloads, log stack traces, and configuration specs.
- Background `#F1F5F9` (light) / `#0D1117` (dark) with 1px border. 
- Integrated copy-to-clipboard action icon in the upper-right corner. Text rendered in `code-sm` with active line-height (`16px`) and subtle line numbering.