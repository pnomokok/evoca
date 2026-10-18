# Evoca web design

One brand, three surfaces, each with its own character. Tokens live in `src/index.css` (`:root`); surface styles
in `src/styles/`.

## Surfaces

| Surface | Character | Rules |
| --- | --- | --- |
| Landing | Tells the story | Editorial, photographic, long scroll. The only place with stock photos. |
| Device (Fatma's living room) | An object, not a web page | Dark warm screen in a bezel. Very large type, few elements, state readable from across the room (clock, light, listening, thinking, speaking). No menus, no scrolling, no small print on the screen. |
| Family panel | A warm family journal | Story and voice first. One primary element per screen (one terracotta button). Paper backgrounds, serif headings. |

The stage ("Watch the loop", demo only) shows the device and the panel side by side; it adds no style of its own
beyond the frames (bezel, phone). Everything demo-only (person picker, stage, clock, reset, exit) lives in the thin
honey "Demo" strip above the product (`styles/navigation.css`); the product surfaces never link to the device or
to another person's view. Pages and URLs: `docs/web-navigation.md`.

## Colour

Keep the existing tokens; do not add one-off hex values in components.

| Token | Use |
| --- | --- |
| `--bg-ivory`, `--bg-paper-light`, `--bg-paper`, `--bg-white` | Page, sunken areas, borders, cards |
| `--text-charcoal`, `--text-charcoal-muted`, `--text-charcoal-faint` | Text: body, helper, labels |
| `--accent-terracotta` (+ `-hover`, `-soft`) | The one primary action per screen; "mine" states |
| `--accent-sage` (+ `-soft`) | Done, answered, recorded |
| `--honey` (+ `-soft`), `--glow` | Light and warmth: the invitation light, "now" in a journey, the device's rings. `--accent-gold` is an alias of `--honey`. |
| `--device-bezel`, `--device-screen`, `--device-text`, `--device-dim` | The device only |
| `--danger` | Destructive actions and errors |

## Type

Serif (`--font-serif`, Newsreader) for headings, story titles, quotes and everything on the device.
Sans (`--font-sans`, Plus Jakarta Sans) for UI. Mono (`--font-mono`) only for the technical style.

| Token | Size | Use |
| --- | --- | --- |
| `--text-label` | 11.5px, 600-700, uppercase, tracked | Eyebrows, chips, field labels |
| `--text-helper` | 13px | Helper text, metadata, timestamps |
| `--text-body` | 14.5px | Body |
| `--text-lead` | 18px serif | Quotes, question text |
| `--text-title` | 24px serif | Card and dialog titles |
| `--text-display` | 32px serif | Page titles |

Labels are never larger than helper text. On the device, sizes scale with the screen (container units): the clock
about 16% of the screen width, a reason or caption about 5%.

## Space and radius

Spacing steps `--space-1` ... `--space-8`: 4, 8, 12, 16, 24, 32, 48, 64 px. Radius: `--radius-sm` 8 (inputs,
buttons), `--radius-md` 14 (small cards), `--radius-lg` 20 (cards, dialogs), `--radius-xl` 28 (device screen),
`--radius-full` (pills, avatars).

## Components

- **Buttons** (`.editorial-btn`): `primary` (terracotta, one per screen), `secondary` (paper, bordered), `quiet`
  (text only, for "Cancel", "Exit demo"), `destructive` (danger text and border; filled only inside its confirm
  dialog). Every button and link shows the focus ring: `outline: 3px solid var(--focus-ring); outline-offset: 2px`
  on `:focus-visible`.
- **Inputs**: paper-light background, `--border-paper-dark` border, `--radius-sm`, 15px text; the label above in
  label style; errors below in `--danger` at helper size, linked with `aria-describedby`.
- **Modal** (`Modal.jsx`): title row (serif title), body, action bar right-aligned with the primary last. Escape
  and the backdrop close it; a bottom sheet below 600 px.
- **Empty states**: one sentence that says what will appear and how (never "No data"), plus at most one action.
- **Error states**: neutral words ("Not available", "We couldn't reach Evoca"); never reveal whether something
  private or declined exists.
- **Toasts** (`.toast-popup`): one line, bottom right, 3.8 s; `role="status"`; errors with the alert icon.
- **Avatars** (`Avatar.jsx`): initials on a colour picked from the person id. There are no person photos in the
  data model; never show a stock or generated face for a person.
- **Story photo or designed card**: a story's own photo when it has one, else the designed text card (period,
  title, teller). Never an empty image box, never a stock photo standing in for a story.

## Technical style

For the judge-facing trace and latency under the device: `--font-mono` at 12px, `--text-charcoal-muted` on
`--bg-paper-light`, dashed row rules, right-aligned milliseconds. No colour except `--danger` for a failed tool.
It sits outside the device frame; it is never on the elder's screen.
