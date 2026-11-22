# D0 – Design foundation: colours, type, buttons, cards, header and logo

Branch: `design-0-foundation` (from `design`, merged back into `design`)
Tests: `tests/test_design_foundation.py`

Decision: `docs/decisions.md`, D21. D16, D19 and D20 left the look of the app to a later design phase. This is the first of three design tasks. D1a (`specs/d1a-design-home-rooms.md`) and D1b (`specs/d1b-design-vote-result.md`) build on it and start only after D0 is merged into `design`. `main` is not touched until D1a and D1b are reviewed and the whole `design` branch is merged in one step.

## Why
The features were built for function first. On a phone the pages are long lists of plain links, headings and grey forms, and buttons and menus are hard to find. Before the pages can be redesigned one by one, they need one shared look: colours, type, buttons, cards and a header that every page uses. Doing this once, first, keeps D1a and D1b from inventing two different styles and from editing the same lines.

## Reference
- The agreed draft (phone screens for home, create a room, my rooms, my groups, room as host, surprise room, rating card, result, join and lobby) is shared in the team as a Claude Design canvas.
- Screenshots of every page before the redesign (380 px and 1280 px, light and dark): `docs/design/before/`.

## What

### Decisions in this spec (please check in the review)
- **One theme for light and dark mode:** a dark blue background (`#0B1F4D`), lighter blue buttons (`#2563EB`), white text, two accent colours (yellow `#FFC94D`, light blue `#7DD3FC`) and white cards with dark text. The app looks the same in both modes, so both are checked but neither needs its own palette. All text meets 4.5:1 contrast.
- **Colours are CSS custom properties** on `:root` in `app.css` (`--einig-bg`, `--einig-surface`, `--einig-button`, `--einig-text`, `--einig-muted`, `--einig-accent`, `--einig-accent-2`, `--einig-card`, `--einig-card-text`). Pico's own variables (`--pico-background-color`, `--pico-color`, `--pico-primary-background`, …) are set from them, for both `prefers-color-scheme` values. Pico classless stays.
- **Type:** the system font stack (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`). No font files and no external fonts (AGENTS.md, privacy). Headings bold, slightly tighter line height.
- **Buttons:** at least 48 px high, 16 px corner radius, full width on a phone. The main button is the lighter blue; `.secondary` is a see-through white outline.
- **Cards:** `article` and the new `.card` class get 24 px corners and a white or see-through-white surface. Space between blocks is 16 px on a phone.
- **Logo:** `app/static/img/logo.svg`, the word "Einig" in Fredoka Bold (SIL Open Font License) as outlines, with the two i-dots in the two accent colours. It is a file in the app; no font is loaded. About 3 KB.
- **Header in `base.html`:** the `My rooms` link on the left (styled as a pill button; its text stays exactly `My rooms`, A8's test), the logo on the right as `<img src="/static/img/logo.svg" alt="Einig">`. Pages may add their own back link in their content.
- **`app.css` gets three marked sections:** `/* D0 foundation */`, `/* D1a home, groups, room */` and `/* D1b vote, lobby, result */`. Each design task writes only in its own section, so the two parallel tasks never edit the same lines. Existing rules that tests rely on (C11's `.rating-screen`, `.swipe-ready` and `:focus-within` rules, B6's `.room-columns`) stay where they are.
- **No HTML structure changes in D0** apart from the header. Texts, forms, routes and the order of elements in the HTML stay as they are, so the page tests keep their meaning. Any new visual order is done in CSS (D1a, D1b).

### Code
- `app/static/img/logo.svg` (new), `app/templates/base.html` (header), `app/static/css/app.css` (tokens, base styles, section markers).
- No Python, no JavaScript, no new dependency.

Checks (one line = one test), `tests/test_design_foundation.py`:
- [ ] Every main page (home, room, lobby, rating page, result, group page, 404) shows the logo as an `<img>` with `alt="Einig"` and a local `/static/img/logo.svg` source.
- [ ] `/static/img/logo.svg` is served with status 200 as SVG and contains no `https://` link and no `<script>`.
- [ ] `app.css` defines the design colours as custom properties on `:root`.
- [ ] `app.css` has the three section markers, in the order D0, D1a, D1b.
- [ ] The header keeps the `My rooms` link to `/` on every page (as A8).

All existing tests stay green and unchanged.

## Not in this task
- The layout of single pages (D1a, D1b).
- Any change to routes, forms, texts the tests check, or `swipe.js`.
