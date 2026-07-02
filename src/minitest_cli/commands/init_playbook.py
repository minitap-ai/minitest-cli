"""The onboarding playbook printed by `minitest init`.

This is the prompt an AI coding agent runs, in the user's app repo, to go from
nothing to a wired test suite (app, personas, scenarios, dependencies, build, runs).
"""

PLAYBOOK = """\
# Minitest onboarding

You are onboarding this mobile/web app to Minitest, an AI testing platform. Work
through the steps below in order, in this repository. Use the `minitest` CLI for
every Minitest action. Run `minitest <group> --help` if you are unsure of a flag.
Pass `--app <id>` on any command when more than one app could match.

## 1. Authenticate
Run `minitest auth login` and wait for it to finish. If a session already exists
it will say so — continue without re-authenticating.

## 2. Determine or create the app
Run `minitest apps list` first. Prefer reusing the existing app whose name matches
the app you were asked to onboard — it was just created for you; do NOT create a
duplicate. Note its app id.

Only if no app matches, inspect the repo to detect the platform (iOS: `.xcodeproj`
/ Swift; Android: Gradle / Kotlin; web: a web frontend) and create it:
`minitest apps create --name "<App Name>" --platform <ios|android|web> [--platform ...]`

## 3. Define personas (test profiles)
Scan the codebase for the user types the app supports (e.g. logged-out visitor,
standard user, admin). Create one test profile per persona.

Default to email-OTP personas: give each a `<prefix>@qa.minitap.ai` username and NO
password. The Minitest agent receives mail for any `@qa.minitap.ai` address and reads
login codes from that inbox at runtime, so it can sign in (or sign up) without you
managing real credentials:
`minitest test-profile create --name "<Persona>" --username "<persona>@qa.minitap.ai" --about "<short description>"`
A non-`@qa.minitap.ai` username with no password is rejected — keep the domain.

Only when the user gives you a real account they own (and the app needs a password)
pass both, via stdin for the password:
`printf '%s' "<password>" | minitest test-profile create --name "<Persona>" --username "<real-email>" --password-stdin --about "<short description>"`

To exercise a flow that needs a specific account state (e.g. a Pro/premium account),
proactively create a `<something>@qa.minitap.ai` persona WITH an explicit password, then
ask the user to link that exact email+password combo to a pro/specific-state account in
their backend — the `@qa.minitap.ai` address keeps the inbox readable for any OTP while
the password lets them pre-provision the account state.

Every scenario is bound to a persona. If you create one without any, the backend
auto-binds the system "New user" persona: a genuine brand-new user that gets a fresh
disposable `<random-str>@qa.minitap.ai` inbox each run, signs up via OTP when the flow
needs an identity, and proceeds anonymously where the app allows it. Use it deliberately
for first-launch, guest, registration, and anonymous flows — don't create your own
anonymous profile (the "New user" persona is system-managed and immutable).
Record each returned profile id.

## 4. Map the user journeys
Run `minitest flow-types list` to see the valid scenario types. Read the app's
navigation, screens, and features and map ALL the main user paths the app
genuinely warrants — every key journey, not just a sample. Cover the happy paths
AND, especially, the paths that can BREAK: failure states, validation errors,
permission/auth denials, empty states, and important edge cases. These are what
real testing must catch. Write goal-oriented acceptance criteria (each criterion
is a job to be done, not a micro-step).

## 5. Create scenarios, wired together
Create one user story per journey. Create prerequisites BEFORE the scenarios that
depend on them, and pass the returned ids to `--depends-on`:
`minitest user-story create --name "<Scenario>" --type "<flow type>" --criteria "<acceptance criterion>" [--criteria ...] --profile "<persona id>" [--depends-on "<prerequisite story id>" ...]`
Dependencies are validated server-side (same app, must exist, no cycles).

When a criterion involves offline behaviour, word it as "Offline (wifi off)" — the
cloud test devices have no airplane mode, so never write "airplane mode".

If a scenario needs a file present on the device (e.g. a document to upload, a photo
to attach), upload it and bind it to the story so it is seeded before the run:
`minitest test-file upload <path>` (record the file id), then
`minitest user-story-binding set-files <story id> --file <file id> [--file ...]`
(`minitest user-story-binding list-files <story id>` shows what is bound). This is
uncommon — only do it when the journey genuinely depends on a pre-seeded file.

## 6. Verify the dependency graph
Run `minitest apps dependencies` and review the wiring. Fix mistakes with
`minitest user-story update` or `minitest user-story-binding set-profile`.

## 7. Hand off to the web app to run
This is where `minitest init` stops. Do NOT upload a build and do NOT start runs
from the CLI — that is the web app's job now. The user still has the Minitest web
app open on the onboarding screen; the app, personas, scenarios, and dependency
graph you just created make a **"Run tests"** button appear there. Tell the user to
click it: that opens a dedicated screen which handles getting a build and launching
the suite for them.

Finish by summarizing what you created — the app, the personas, the scenarios, and
the dependency wiring — so the user knows exactly what will run when they click
**Run tests**.
"""
