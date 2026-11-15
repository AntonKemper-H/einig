# C1c – Several requests at once on Render (gunicorn workers and threads)

Branch: `feature-c1c-gunicorn-workers`
Tests: `tests/test_gunicorn_workers.py`

## Why
The deployed app starts gunicorn with its defaults: one sync worker, so one request at a time. Since C2b (PR #18) the room page calls Google Place Details and every photo goes through `/photo/...`, each with a 5 s timeout, so one slow Google answer makes every other user wait up to 5 s (review of PR #18, Timonhio). C2b already stops calling Google after the first timeout on a page; this task is the server-side half: let the server handle several requests at the same time.

## The change
`render.yaml`, `startCommand` (the `init-db` part stays as it is):

```
uv run --no-dev flask --app app init-db && uv run --no-dev gunicorn --workers 2 --threads 4 --timeout 30 --bind 0.0.0.0:$PORT "app:create_app()"
```

- `--workers 2`: two separate Python processes. If one hangs or crashes, the other one keeps answering.
- `--threads 4`: each worker handles up to 4 requests at once. With threads > 1 gunicorn switches to its `gthread` worker by itself (measured: the log says `Using worker: gthread`). Up to 8 requests run at the same time. Our requests mostly *wait* (for Google or the database), so threads are enough; Render's free plan has only 0.1 CPU, so more processes would not make anything faster.
- `--timeout 30`: gunicorn's default, written out so it is visible. With `gthread` it restarts a worker process that stops responding for 30 s; it does not cut off a single slow request (the photo and details calls already stop after 5 s themselves).
- No new dependency: gunicorn is already pinned (`gunicorn==27.0.0`), and `gthread` is part of it.

### Fits Render's free plan (512 MB RAM)
Measured locally with exactly these flags (macOS, SQLite, after 20 parallel requests): gunicorn master about 34 MB, each worker about 55 MB, the `uv run` wrapper about 24 MB, **about 170 MB in total**. Threads share their worker's memory, so they add very little. That leaves plenty of room below 512 MB. Three or more workers would also fit, but would only cost memory on 0.1 CPU.

### The app is thread-safe
- Flask's `g` and `request` belong to one request (one app context), also when several threads run in the same process.
- `app/db.py` opens one database connection per request in `g.db` and closes it at the end (`close_db`). Threads never share a connection.
- Module-level variables in `app/` are only constants (messages, field masks, `POINTS`, …) that are never changed while the app runs.
- `services/places.py` calls `requests.get`/`requests.post` without a shared `Session`, so threads share nothing there either.
- At most 8 database connections are open at once (2 × 4). Neon's free plan allows far more.
- `init-db` still runs once, before gunicorn starts, not once per worker.

## What
- [ ] `render.yaml`'s `startCommand` starts gunicorn with `--workers 2`.
- [ ] … with `--threads 4`.
- [ ] … with `--timeout 30`.
- [ ] The three flags belong to the gunicorn command, not to the `init-db` command before it.
- [ ] gunicorn still binds `0.0.0.0:$PORT` and still loads `"app:create_app()"`.
- [ ] Edge case (memory): no more than 2 workers, so the app stays well inside 512 MB.
- [ ] Edge case (concurrency): at least 2 requests can run at the same time (workers × threads ≥ 2).
- [ ] Thread safety: two requests running in two threads at the same moment each get their own database connection, and both connections are closed afterwards.
- [ ] Thread safety: `close_db` is registered to run at the end of every request (app context).
- [ ] Thread safety, accepted action: rooms created from several threads at the same time are all saved, each with its creator; none is lost.

Restart/persistence: nothing is stored by this task. That accepted data survives a restart is already covered by `tests/test_deployment.py`.

## Out of scope
- Changes to `tests/test_deployment.py` (reviewed). It already checks that `init-db` runs before `gunicorn`.
- A gunicorn config file, async workers (gevent/eventlet), `--preload`, or a connection pool: not needed at this size, and gevent would be a new dependency.
- Caching Google answers, or any other change to C2b.
- Changing the Render plan.

## Manual step on Render (important)
The Render service was created by hand, **not** via the Blueprint, so Render does not read `render.yaml`. After the merge, a human (Track C) must paste the new start command into **Render dashboard → einig → Settings → Start Command** and deploy. Afterwards the deploy log must show `Using worker: gthread` and two `Booting worker` lines.

## Done when
- All tests in `tests/test_gunicorn_workers.py` and all earlier tests pass (`uv run pytest`), output pasted in the PR.
- The start command is changed in Render's dashboard after the merge, and the deploy log shows `Using worker: gthread` and two workers (checked by hand).
- Work is on branch `feature-c1c-gunicorn-workers`, pushed, pull request opened for review by Track B (Timonhio, D10).
