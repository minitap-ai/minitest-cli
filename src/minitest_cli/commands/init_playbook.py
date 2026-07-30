"""Offline fallback for the onboarding playbook printed by `minitest init`.

The playbook is served by Minitest (`init_helpers.load_playbook`) so it evolves with
the suite-design methodology it delegates to. This copy is only used when the server
is unreachable or the agent has not authenticated yet, so keep it in step with
testing-service's `cli-onboarding` channel template.
"""

FALLBACK_PLAYBOOK = """\
# Minitest onboarding

You are onboarding this repository to Minitest: you will design and create a
test suite for the app in the current working directory. A human is with you —
they have the Minitest onboarding screen open in their browser.

## Before anything else

1. `minitest auth login` if you are not authenticated yet.
2. `minitest apps list --json`. An app has very likely **already been created
   for you** — reuse the one that matches this repository. Do **not** create a
   duplicate. Only if none matches, detect the platform from the repo
   (`.xcodeproj`/Swift → ios, Gradle/Kotlin → android, web frontend → web) and
   run `minitest apps create --name "<app>" --platform <platform> --json`.
3. `minitest capabilities --platform <ios|android|web>`, once per platform the
   app targets. A criterion that needs something the testing agent cannot
   perform or observe on that platform fails as unprocessable, not because the
   app is broken — so every criterion you write later must sit inside that
   envelope.

## Then follow the suite-design methodology — do not improvise one

Load the `minitest-cli` skill and follow its full test-suite design workflow
(`reference/test-suite-design.md`) from start to finish. That document is the
single source of truth for *how* to build the suite; this playbook only tells
you *where you are*. In particular, do not skip:

- The questions you must ask the human **before reading any application code** —
  sources of truth first, then context, then scope.
- Delegating all code investigation to scoped subagents rather than reading the
  codebase yourself. If your host has no subagent mechanism, run each dispatch
  yourself, sequentially, exactly as the document's fallback describes.
- The ordered waves — recon, surface mapping, the gating hunt, state analysis,
  design, adversarial verification — and the artifacts each one produces.
- Both hard stops: the human confirms the persona catalog is provisionable
  before you go further, and the human explicitly approves the final suite
  before you run a single creating CLI command.

Work in a throwaway directory (`mktemp -d`), never write artifacts into this
repository.

## Where you stop

Creating the suite through the CLI is the last thing you do. Do **not** upload a
build and do **not** start a run from the CLI — the human's onboarding screen
shows a "Run tests" button once the suite exists, and that is how the first run
is launched. Finish by summarising, in plain product language, the personas and
scenarios you created and what the human should check.
"""
