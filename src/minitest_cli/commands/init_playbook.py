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

## 7. Get a build to test
You already know the platform from step 2 — do not ask. Find or obtain an
installable build that runs on an emulator/simulator on the first try. First search
the repo for an existing artifact (`build/`, `DerivedData`, `**/outputs/apk/**`,
release folders). If none exists, ask the user whether they have one (get the path)
or want you to build it. Guardrails:
- Android: an x86_64 / universal DEBUG `.apk` (debug-signed; avoid release/unsigned
  builds that need a keystore).
- iOS: a Simulator build (simulator arch, no code signing; NOT a device build that
  needs a provisioning profile).
- React Native / Expo: the JS bundle MUST be embedded (release-style bundling), NOT
  served from the Metro dev server — a dev client hangs waiting for Metro.
Then upload it: `minitest build upload <path>` (add `--app <id>` if more than one
app could match). The build is stored against the active app from step 2, so it
shows up in the web app scoped to that app and is reusable across runs. Record the
build id.

## 8. Run the suite
Run every scenario against the build:
`minitest run all [--ios-build <id>] [--android-build <id>]`
(or `minitest run start "<scenario>"` for a single one). Report the pass/fail
results and the reason for any failure back to the user.
"""
