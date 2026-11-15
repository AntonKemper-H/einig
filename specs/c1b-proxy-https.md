# C1b – Invite link with https behind Render's proxy

Branch: `feature-c1b-proxy-https`
Tests: `tests/test_proxy_headers.py`

## Why
Render ends HTTPS at its proxy and talks plain http to the app, so `url_for(..., _external=True)` builds the invite link (A2) as `http://nod-lqeq.onrender.com/rooms/…`. The link works but costs every guest a redirect from http to https, and the QR code from A6 (PR #16) encodes the same URL. The app must therefore read the scheme and host from Render's `X-Forwarded-*` headers – but only when it is told it runs behind exactly one proxy, because otherwise any client could send these headers itself and fake the scheme and host.

Measured on `main` with the test client before this task:
- proxy headers not read, `X-Forwarded-Proto: https` → `http://nod-lqeq.onrender.com/…`
- proxy headers read, `X-Forwarded-Proto: https` → `https://nod-lqeq.onrender.com/…`
- proxy headers read, no header (local run) → `http://localhost/…` (unchanged)

`PREFERRED_URL_SCHEME` is not an alternative: inside a request Flask takes the scheme from the request itself, so the setting has no effect on the invite link (measured).

## What

### Switch `TRUST_PROXY_HEADERS`
- [ ] Real run: the environment variable `TRUST_PROXY_HEADERS` set to `1` or `true` (any case, surrounding spaces ignored) sets `app.config["TRUST_PROXY_HEADERS"]` to `True`.
- [ ] Real run: the variable missing, empty, `0`, `false` or any other value leaves the switch off (`False`). Off is the default, so the local dev server is not affected.
- [ ] Tests set the switch only through the test config (`{"TRUST_PROXY_HEADERS": True}`); the environment is ignored there, as for every other setting.

### Switch on (deployed on Render)
- [ ] The app wraps its WSGI app in `werkzeug.middleware.proxy_fix.ProxyFix` with `x_for=1, x_proto=1, x_host=1` (exactly one proxy in front). werkzeug comes with Flask, so there is no new dependency.
- [ ] Accepted: a request with `X-Forwarded-Proto: https` and `Host: nod-lqeq.onrender.com` shows the invite link `https://nod-lqeq.onrender.com/rooms/<room_id>` on the room page, and no `http://` invite link.
- [ ] Accepted: `X-Forwarded-Host` is used as the host of the invite link.
- [ ] Edge case: without any `X-Forwarded-*` header the invite link stays `http://localhost/rooms/<room_id>`, as before.
- [ ] The invite link in the text field, in the link target (`href`) and in the link text is the same URL. The QR code from A6 is built from this same `invite_url` value, so it follows automatically; its own test belongs to A6 (PR #16), not to this task.

### Switch off (default, local)
- [ ] Rejected: `X-Forwarded-Proto: https` and `X-Forwarded-Host: evil.example` are ignored: the invite link stays `http://localhost/rooms/<room_id>` and never mentions `evil.example`.
- [ ] The WSGI app is not wrapped in `ProxyFix`.

### Nothing else changes
- [ ] Creating a room still stores the room and its creator, whether the switch is on or off (no saved data depends on the switch).
- [ ] `GET /health` still answers `ok` with the switch on.

## Out of scope
- `SESSION_COOKIE_SECURE`, HSTS, forced redirects from http to https inside the app.
- Any change to A6 (PR #16) or PR #18; A6 profits from this without being touched.
- Changes to `tests/test_deployment.py` (reviewed) or to `render.yaml` beyond listing the new variable.
- Setting the variable on Render: a human does this in the dashboard after the merge (the service was created by hand, so Render does not read `render.yaml`).

## Done when
- All tests in `tests/test_proxy_headers.py` and all earlier tests pass (`uv run pytest`), output pasted in the PR.
- `.env.example` and `render.yaml` list `TRUST_PROXY_HEADERS` (empty locally, `true` on Render).
- After the merge and `TRUST_PROXY_HEADERS=true` in Render's Environment, the room page on https://nod-lqeq.onrender.com shows an `https://` invite link (checked by hand).
- Work is on branch `feature-c1b-proxy-https`, pushed, pull request opened for review by Track B (Timonhio, D10).
