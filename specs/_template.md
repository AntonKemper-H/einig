# <Feature ID> – <Task name>

## Why
<Two sentences: what this is for. Used to pick the safe reading of anything ambiguous.>

## What
<!-- One line per thing that must be true. One line = one test. Reference F-IDs from docs/concept.md. -->
- [ ] <accepted action and its visible result>
- [ ] <rejected action: message shown, saved data unchanged>
- [ ] <edge case>
- [ ] <after a restart, accepted changes are still there>

## Out of scope
<!-- The fence. Name what the agent will be tempted to do. -->
- <…>

## Done when
- All tests in `tests/<file>.py` pass (`uv run pytest`), output pasted.
- Accepted action visible in the app; rejected action shows a message and changes nothing.
- Accepted changes survive an app restart.
- Work is on branch `<branch-name>`, pushed, pull request opened for review.
