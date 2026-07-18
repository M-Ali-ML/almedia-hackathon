---
name: Sentinel Core
colors:
  surface: "#f8f9ff"
  surface-dim: "#cbdbf5"
  surface-bright: "#f8f9ff"
  surface-container-lowest: "#ffffff"
  surface-container-low: "#eff4ff"
  surface-container: "#e5eeff"
  surface-container-high: "#dce9ff"
  surface-container-highest: "#d3e4fe"
  on-surface: "#0b1c30"
  on-surface-variant: "#45464d"
  inverse-surface: "#213145"
  inverse-on-surface: "#eaf1ff"
  outline: "#76777d"
  outline-variant: "#c6c6cd"
  surface-tint: "#565e74"
  primary: "#000000"
  on-primary: "#ffffff"
  primary-container: "#131b2e"
  on-primary-container: "#7c839b"
  inverse-primary: "#bec6e0"
  secondary: "#515f74"
  on-secondary: "#ffffff"
  secondary-container: "#d5e3fd"
  on-secondary-container: "#57657b"
  tertiary: "#000000"
  on-tertiary: "#ffffff"
  tertiary-container: "#271901"
  on-tertiary-container: "#98805d"
  error: "#ba1a1a"
  on-error: "#ffffff"
  error-container: "#ffdad6"
  on-error-container: "#93000a"
  primary-fixed: "#dae2fd"
  primary-fixed-dim: "#bec6e0"
  on-primary-fixed: "#131b2e"
  on-primary-fixed-variant: "#3f465c"
  secondary-fixed: "#d5e3fd"
  secondary-fixed-dim: "#b9c7e0"
  on-secondary-fixed: "#0d1c2f"
  on-secondary-fixed-variant: "#3a485c"
  tertiary-fixed: "#fcdeb5"
  tertiary-fixed-dim: "#dec29a"
  on-tertiary-fixed: "#271901"
  on-tertiary-fixed-variant: "#574425"
  background: "#f8f9ff"
  on-background: "#0b1c30"
  surface-variant: "#d3e4fe"
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: "700"
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: "600"
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: "600"
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: "400"
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: "400"
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: "600"
    lineHeight: 16px
    letterSpacing: 0.05em
  mono-data:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: "400"
    lineHeight: 18px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  container-margin: 32px
  column-gutter: 20px
---

## Brand & Style

The design system is engineered for high-stakes decision-making environments where clarity, speed, and trust are paramount. The brand personality is **authoritative yet approachable**, functioning as a sophisticated co-pilot for fraud analysts.

The aesthetic follows a **Corporate Modern** direction with a focus on high-information density without visual clutter. It prioritizes a clean, systematic interface that minimizes cognitive load. By utilizing heavy whitespace and a restricted color palette, the system directs focus toward critical data anomalies and risk indicators. The emotional response should be one of "calm control"—the user feels empowered by the data rather than overwhelmed by it.

## Colors

The palette is anchored by **Deep Navy (#0F172A)**, used for primary navigation and high-level headers to establish structural authority. The background is a **Crisp White/Off-White (#F8FAFC)** to reduce eye strain during prolonged analysis sessions.

Status colors are strictly functional:

- **Emerald (#059669):** Used for verified identities and low-risk scores.
- **Amber (#D97706):** Reserved for manual review flags and suspicious patterns.
- **Crimson (#DC2626):** High-alert indicators and confirmed fraudulent activity.

Neutral slates are used for secondary text and decorative borders to maintain a low-contrast environment that makes status colors "pop" when they appear.

## Typography

The design system utilizes **Inter** for all UI elements due to its exceptional legibility and tall x-height, which is critical for reading long strings of alphanumeric data (like transaction IDs or hashes).

**Key Rules:**

- **Headlines:** Use Bold weights with slight negative letter-spacing for a modern, compact feel.
- **Body:** Standard body text remains at 14px for optimal density in dashboard environments.
- **Data Tables:** For transaction IDs and IP addresses, use a secondary monospaced font (JetBrains Mono) at a slightly smaller scale to distinguish system data from human-readable labels.
- **Hierarchy:** Use color (Slate 900 vs Slate 500) rather than dramatic size shifts to establish hierarchy in dense data views.

## Layout & Spacing

This design system uses a **Fluid 12-column grid** for main dashboard views, allowing content to stretch and fill the screen while maintaining strict margins.

**Responsive Adjustments:**

- **Desktop (1440px+):** 32px external margins, 20px gutters. Content is housed in modular cards.
- **Tablet (768px - 1024px):** 24px external margins, side navigation collapses into an icon-only rail.
- **Mobile (Under 768px):** 16px margins. Cards stack vertically. Navigation moves to a bottom bar or hamburger menu.

Spacing follows a linear 4px/8px scale. Complex data tables should use "Compact" spacing (8px vertical padding) while marketing or settings pages use "Spacious" spacing (16px+ vertical padding).

## Elevation & Depth

To maintain a professional and clean aesthetic, depth is achieved through **low-contrast outlines and subtle ambient shadows.**

- **Base Layer:** The background (#F8FAFC) is the lowest level.
- **Surface Layer:** White cards (#FFFFFF) sit on the background. They feature a 1px border (#E2E8F0) and a very soft, diffused shadow: `0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)`.
- **Active Layer:** Modals and dropdowns use a higher elevation with a more pronounced shadow to create a clear "overlay" effect: `0 20px 25px -5px rgba(0, 0, 0, 0.1)`.

Avoid heavy gradients or skeuomorphism. Depth should feel "paper-thin" and layered.

## Shapes

The design system adopts a **"Soft Professional"** shape language.

- **Standard Radius:** 8px (0.5rem) for smaller components like input fields and buttons.
- **Large Radius (rounded-lg):** 16px (1rem) for main dashboard containers and cards. This provides a contemporary, friendly feel that balances the "seriousness" of the deep navy palette.
- **Icon Enclosures:** Small circular backgrounds for status icons (e.g., a green circle behind a checkmark).

## Components

### Buttons

- **Primary:** Solid Deep Navy (#0F172A) with white text. 8px radius.
- **Secondary:** White background with a 1px Slate-200 border.
- **Danger:** Solid Crimson (#DC2626) for irreversible actions like "Block User."

### Data Cards

Main containers for dashboard widgets. Must include a 16px padding and a subtle header separator. Use `rounded-lg` (16px) for the outer container.

### Status Chips

Small, low-profile badges for transaction status.

- **Safe:** Light emerald background with dark emerald text.
- **Fraud:** Light crimson background with dark crimson text.
- Shape: Fully rounded (pill) to distinguish them from interactive buttons.

### Input Fields

Bordered style (1px Slate-200). On focus, the border transitions to Primary Navy with a subtle outer glow. Place labels above the field in `label-md` typography.

### Data Tables

Rows should have a subtle hover state (#F1F5F9). Avoid vertical borders; use thin horizontal dividers for a cleaner, modern look. The header row should be slightly darker or use the `label-md` typography style.
