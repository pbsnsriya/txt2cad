# Components

Sizes, radii and layout were set at 1440x900 and are expressed as tokens (`tokens.json`). Colours are named by role (surface, border, accent, ...) so the palette can change without touching a component. Every spec lists its states, including focus, disabled, loading, error and empty. Icons: Lucide (MIT). Font: Inter Variable (OFL).

Global rules
- Focus ring on every interactive element: `focus-visible`, 2px `accent` ring with 2px offset (3:1 or better against bg and surface, checked in contrast report).
- Hit target at least 32px high for icon buttons in dense panels, 40px elsewhere.
- Motion: `fast` 120ms for hover/press, `base` 200ms for panels and menus. Respect `prefers-reduced-motion`: no transforms, opacity only.
- Theme: `data-theme="light|dark"` on `<html>`; default follows the OS; the toggle writes the choice to localStorage inside try/catch.
- Never colour alone: status uses an icon or text label next to the colour.

## Layout shell (Workspace, Sidebar, Assistant)

```
Shell
  regions   sidebar 270px (collapses to 56px) | main (topbar 59px, tabbar 56px, content) | assistant 390px
  states    sidebar open/collapsed, assistant open/closed, narrow (< 900px: assistant becomes an overlay sheet)
  resize    drag handle on the growing edge; arrow keys nudge 8px; double-click resets; clamp so the viewer keeps >= 340px
  tokens    bg app canvas, surface panels, border 1px
  a11y      landmarks: nav (sidebar), main, complementary (assistant); handles are role="separator" with aria-orientation, aria-valuenow
  used on   Workspace, Sidebar, Assistant, Viewer, Analysis tabs
```

## Button

```
Button
  variants  primary (accent fill), secondary (surface + border), ghost (no border), danger
  sizes     sm 32px, md 40px
  states    default, hover (one step darker/lighter), active, focus-visible, disabled (opacity .5, aria-disabled), loading (spinner left, label kept, aria-busy)
  tokens    primary: bg accent, text on-accent. secondary: bg surface, border border, text fg. radius md, font sm/500
  a11y      real <button type="button">; disabled uses the disabled attribute; loading keeps the accessible label
  used on   Home (Open IFC...), Export menu, Analysis tabs, Version history
```

## IconButton

```
IconButton
  variants  ghost, secondary, accent (send)
  sizes     sm 32px, md 40px (round for send / attach, radius pill)
  states    as Button
  a11y      always has aria-label (for example "Send", "Attach image", "Switch to dark theme"); tooltip on hover and focus
  used on   Home composer, Workspace TopBar, Sidebar sidebar (collapse, search), Viewer view palette
```

## SplitButton (Export)

```
SplitButton
  parts     main action "Export IFC" + caret that opens a Menu
  states    default, hover per part, disabled while nothing to export ("Nothing to export yet" as title), busy
  a11y      two buttons; caret has aria-haspopup="menu", aria-expanded
  used on   Export menu (TopBar)
```

## Menu (dropdown)

```
Menu
  items     title + one-line description + optional icon (Export menu has 11+ items, each with a sub-line)
  states    open/closed, item hover/focus, item disabled with reason, item busy
  behaviour opens under the trigger, closes on Escape / outside click, arrow keys move, Enter activates, type-ahead
  tokens    bg surface, border border, shadow pop, radius lg
  a11y      Radix DropdownMenu (role menu, menuitem)
  used on   Export menu, Workspace "..." more menu, Home model picker
```

## Prompt composer

```
Composer
  parts     auto-growing textarea (min 2 rows, max 10), attach "+" (IconButton), model picker (Menu), send (IconButton accent)
  variants  hero (Home: width <= 758px, radius xl) and docked (Workspace assistant: bottom, radius lg)
  states    empty (send disabled), typing, with attachment thumbnails, drag-over (dashed accent border), running (send becomes Stop), error (inline message under box), disabled (no backend)
  keys      Enter sends, Shift+Enter newline, Esc clears focus; paste image attaches
  a11y      textarea has an associated label (visually hidden), live region announces "Run started / finished / failed"
  used on   Home, Workspace, Composer
```

## Chip (starter prompts)

```
Chip
  variants  outline (default), selected
  states    default, hover, focus-visible, pressed, disabled
  tokens    border border, text fg, radius pill, font sm/400, height 44
  behaviour click fills the composer (does not send)
  a11y      <button>; group has role="group" with a label
  used on   Home
```

## Tabs (file tab + view tabs)

```
Tabs
  items     file chip (name, close x) | 3D model | Drawings | Code review | Cost & carbon
  states    selected (surface bg + border + accent icon), hover, focus-visible, disabled (no data for this version; title explains why), overflow (scroll with edge fade)
  a11y      Radix Tabs: role tablist/tab/tabpanel, arrow keys, disabled tabs stay focusable with aria-disabled and a tooltip
  used on   Workspace
```

## Card / Panel

```
Card
  variants  flat (border only), raised (shadow card), sunken (surface-sunken)
  states    default, hover (for clickable), selected (accent border), loading (skeleton), empty
  tokens    bg surface, border border, radius lg, padding 16
  used on   Home (recorded runs rows use radius md), Assistant version card, Analysis tabs stat cards
```

## ListRow (sessions, recorded runs, clauses)

```
ListRow
  parts     leading icon, title (truncate with ellipsis, full text in title attr), meta (right-aligned)
  states    default, hover, active/selected (accent-soft bg), focus-visible, with delete action on hover/focus
  a11y      row is a button or link; delete is its own button with aria-label "Delete session <name>"
  used on   Home recorded runs, Sidebar sessions, Analysis tabs code-review clauses
```

## Badge / Pill

```
Badge
  variants  neutral, info, success, warning, danger; mono variant for counts ("162 elements")
  tokens    <tone>-soft bg + <tone> text (contrast checked), radius pill, font xs/500
  a11y      status badges include text, not only colour ("Connected", "preview 6 . 118 elements")
  used on   Workspace (version/preview badge), Sidebar (backend status), Analysis tabs (pass / info counts)
```

## Trace (assistant stream)

```
TraceSection
  parts     phase title (with check or spinner), italic rationale paragraph, optional step list (collapsed by default), error row
  states    pending, active (spinner + live "drafting..." line), done, rejected step (danger-soft row, expandable detail), empty
  behaviour auto-scrolls to bottom unless the user scrolled up; "jump to latest" pill appears
  a11y      live region (polite) for the active line; collapsible rows are buttons with aria-expanded
  used on   Assistant, Replay
```

## Viewer overlays

```
ViewPalette       floating card: Top, Bottom, Front, Back, Left, Right, Isometric, Reset, Section toggle. Keys 1-7 as shortcuts. a11y: buttons with labels, group role="toolbar".
SectionSlider     bottom bar: slider (cut height), "full height" label, "follow build" checkbox. a11y: Radix Slider, aria-valuetext "cut at 5.7 m".
InfoCard          bottom-left card: file name, unit, hint text; becomes element properties on selection.
AxisGizmo         decorative, aria-hidden.
CountBadge        mono Badge, top-left of the viewer.
States            loading (spinner + "Loading model..."), error ("could not read this IFC", with the reason), empty ("No model yet").
```

## Table (class counts, schedules)

```
Table
  states    default, row hover, sorted, empty
  tokens    row border border, cell padding 8x12, numeric columns right-aligned tabular-nums
  a11y      real <table>, <th scope>, caption
  used on   Assistant (IFC class counts), Analysis tabs
```

## Form controls

```
Input / Textarea / Select / Checkbox / Switch / Slider
  states    default, hover, focus-visible (accent ring), disabled, invalid (danger border + message with icon), readonly
  tokens    border border-input (3:1 against surface), radius md, height 40
  a11y      label always present (visually hidden is acceptable), error linked with aria-describedby
  used on   Workspace section slider, Home composer, settings (Settings)
```

## Toast / Inline status

```
Toast
  variants  info, success, warning, danger
  behaviour 5s auto-dismiss for info/success; danger stays until dismissed; max 3 stacked; pause on hover
  a11y      role="status" (polite) or role="alert" for danger; dismiss button labelled
  used on   Export menu (export done / failed), image attach (image refused), Settings (profile test)
Inline status (for runs) lives in the Trace and under the Composer, not as a toast.
```

## Dialog (confirm delete)

```
Dialog
  states    open/closed, busy, error
  behaviour focus trap, Escape closes, initial focus on the safe action ("Cancel"), danger button labelled with the object ("Delete session")
  a11y      Radix Dialog (role dialog, aria-labelledby, aria-describedby)
  used on   Sidebar delete session, revert revert confirmation (optional)
```

## Tooltip

```
Tooltip
  behaviour 400ms delay on hover, immediate on keyboard focus, Esc closes, never the only place a label lives
  a11y      Radix Tooltip; trigger keeps its own aria-label
```

## Skeleton / Spinner / EmptyState

```
Spinner      16px and 20px, aria-hidden with a visible text sibling where it blocks something
Skeleton     for version cards and drawing thumbnails; respects reduced motion (static)
EmptyState   icon + one sentence + one action. Examples: "No sessions yet", "Nothing to export yet", "Run a prompt to see drawings here"
```

## Resizer

```
Resizer
  behaviour pointer drag, arrow keys 8px (Shift 32px), double-click reset
  a11y      role="separator", aria-orientation, aria-valuemin/max/now, focusable
```

## Version card (history)

```
VersionCard
  parts     snapshot (static PNG) -> live orbit on hover (max 3 live canvases), prompt text (2 lines), Inspect, IFC / DXF / Bundle buttons, version number badge
  states    snapshot, hover-live, loading, selected (in workspace), failed snapshot (icon + "Preview unavailable")
  a11y      the card is not a button; Inspect is. Live canvas is aria-hidden; the snapshot has alt text with the prompt
  used on   Version history, Assistant
```
