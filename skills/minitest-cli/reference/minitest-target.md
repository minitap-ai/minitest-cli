<!-- rendered by Minitap — do not edit -->
# The Minitest Executor (Mini)

Every scenario you design is ultimately run by **Mini**, the Minitest tester
agent, on a real device or browser. Design within what Mini can physically do and
observe — a scenario that asks for something Mini cannot perform fails as
unprocessable, not because the app is broken. This file is the envelope; consult
it whenever a step or acceptance criterion depends on a device capability,
connectivity, camera, multi-device simultaneity, or an identity/OTP.

## What Mini can and cannot do

Mini is the Minitap testing agent. It drives real Android, iOS and web sessions and executes acceptance criteria. A criterion Mini cannot physically perform or observe will fail as unprocessable, not because the app is broken.

**What Mini can do:**

- **Gestures:** tap (by label, coordinates or screen percentage), long-press, swipe, drag (including pick-up drag with a hold before the move), pinch and zoom. *(Android, iOS, web)*
- **Curved gestures:** an arbitrary path in a single press-move-release — circles, arcs, loops, figure-eights. Rotary dials, knobs, circular unlocks, pattern locks, signature pads and arc sliders are all testable. *(Android, iOS, web)* **Android:** Paths anchor to an element's bounds. **iOS:** Paths anchor to an element's bounds.
- **Text:** type into the focused field or a targeted element, erase, press enter. *(Android, iOS, web)*
- **System navigation:** press back to leave the current screen, and home to send the app to the background. *(Android, iOS)* **Android:** Both are real system key events. **iOS:** Both are gestures, not key events: home is a home-indicator swipe and back is a left-edge swipe, so back only works where the app implements the swipe-back gesture — prefer the app's own back control when it has one.
- **Observation:** screenshots (standard and high-res), a compact or full UI hierarchy, finding elements by text or label, and visual questions. *(Android, iOS, web)*
- **Retrospective transient observation:** inspect recent screen activity after it disappears to identify brief loading, transition, or intermediate UI states. This does not provide precise motion, easing, or sub-100ms continuous-video analysis. Cloud devices only: it reads the cloud screen capture. *(Android, iOS)*
- **App lifecycle:** the harness installs the build and launches the app before the run starts, attaching the agent bridge only when the build carries it. Mini never relaunches the app itself. An app that does not reach the foreground after the harness's bounded launch retries is reported to Mini as an app that did not open: Mini diagnoses it from the screen and fails the story with video — it is not a harness escalation. A launch command that errors or times out is still a Minitap harness failure. *(Android, iOS)*
- **Deep links & URLs:** open a URL to land straight on the screen it targets — an https link, a universal or app link, or a custom scheme. *(Android, iOS, web)* **Android:** The URL goes out as a system VIEW intent, so the app under test receives it exactly as it would from any other app. **web:** Navigates the attached browser. The page under test is already open when the run starts, so navigate elsewhere only when a criterion requires it.
- **Browser state:** set, read and delete cookies and local storage items in the browser — e.g. turn on a feature flag the app reads from a cookie — then reload so the page picks them up. A cookie set without a domain lands on the current page's host. *(web)*
- **API request inspection:** list the HTTP(S) requests the app under test sent and read their headers, request bodies and response bodies, so a criterion can compare what the screen shows against what the backend API returned — e.g. a picker's options against the config endpoint — instead of hard-coding expected values. *(Android, iOS, web)* **Android:** Native apps and web apps in the device browser, on cloud devices. Not for apps that pin their certificates, and not when the run routes through a residential proxy. **iOS:** Native apps and web apps in the device browser, on cloud devices. Not for apps that pin their certificates, and not when the run routes through a residential proxy.
- **Speaker audio:** transcribe what the browser's speakers output, waiting for the next utterance or reading back what was already said. *(web)*
- **Microphone input:** play generated or bound audio into the microphone so voice-driven flows are testable. *(Android, iOS, web)* **Android:** Cloud devices only. WAV and MP3 are accepted; use one-shot playback when the flow must return to silence automatically. **iOS:** Cloud devices only. WAV is the canonical test format; MP3, M4A and AAC are also accepted. Playback may run once or loop until stopped. **web:** Speak text or play an audio file into the browser microphone. Playback is one-shot and blocks until it ends, so there is no loop or stop.
- **Camera:** the camera is simulated — a per-story image or MP4 is fed as the live camera feed (browser webcam on web, device camera on cloud Android and iOS), and on mobile Mini can also feed any image or video itself, including a screenshot of another device, so QR scanning and document presentation are testable. *(Android, iOS, web)* **Android:** Cloud devices only; local emulators have no injectable camera. Non-16:9 videos are squashed to 1280x720; images are letterboxed automatically. **iOS:** Cloud simulators only; apps that scan through AVCaptureMetadataOutput or AVCaptureVideoDataOutput receive the feed, but Expo camera views may not start a session and scanners built on Apple Vision (Flutter mobile_scanner) cannot decode on the simulator yet.
- **Files:** a story can have files bound to it, and the harness places them on the device or machine before the run starts. Placing files is never Mini's job — bound files are listed in the goal under "Test Files" with a `device_path`, and Mini just uses them. A bound file that is missing or that the app cannot see is a Minitap harness failure to escalate to Minitap engineering — never a Mini limitation, and never something to ask the customer for. A file the goal lists as FAILED TO STAGE is the same harness failure: escalate to Minitap engineering naming the file, and do not try to place it yourself. *(Android, iOS, web)*
- **Connectivity:** change the network state mid-run. *(Android, web)* **Android:** Wi-Fi on/off, airplane mode, and reading the connectivity state. **web:** Take the page offline and back online.
- **Screen orientation:** rotate to landscape or portrait. *(Android, iOS)* **iOS:** Cloud simulators only — not available on a physical iPhone.
- **Device state:** grant or revoke permissions without the system prompt, and switch between light and dark appearance. *(Android, iOS, web)* **Android:** Can also simulate the battery level, and the app sees it: the system reports the fake level to every app and its own low-battery behaviour fires. Cloud devices boot with no battery attached, so a simulated level only renders once the battery is marked present. **iOS:** Cloud simulators only — a physical iPhone gets none of this. Can also freeze the status bar to a fixed time and battery for stable screenshots. The battery override is what the status bar draws, nothing more — the app still reads an unknown battery, so write such a criterion against the status bar, never against in-app battery behaviour.
- **Push notifications** (cloud simulators): deliver an arbitrary payload to the app under test. The payload JSON is bound to the story as a test file and seeded before the run. Delivery is not display — iOS drops a notification for an app that never registered for them, so assert on what the screen shows. *(iOS)*
- **Geolocation:** mock GPS, simulate movement along a route at a given speed (m/s), and restore the real location. Mocking feeds a position; it does not grant the app's location permission, which still goes through the app's own prompt. *(Android, iOS)* **Android:** Positions are fed about once a second, so allow a few seconds for a transition.
- **Email inbox:** read any `<prefix>@qa.minitap.ai` inbox at runtime and act on what lands in it — one-time codes, verification and confirmation emails, and magic links — so a signup or login gated on an emailed code can be carried to the end. *(Android, iOS, web)*
- **Third-party OAuth sign-in:** clear a *Sign in with Google* button with a Minitap Google account leased at runtime, including its 2-Step Verification code, swapping to a fresh account when one is broken. The pool is a real Google estate, so the consent and challenge screens sit outside the app under test. *(Android, iOS, web)*
- **Phone-OTP login** — *only when the persona carries both a phone number and a static OTP code.* Minitap owns no phone number and receives no real SMS: the customer whitelists a number and a fixed code in their own staging backend and stores both on the persona. Mini then enters the number and, on the app's OTP screen, the configured code. A persona missing either field cannot pass a phone-OTP screen at all. Configuration guide: https://www.minitap.ai/docs/minitest/suite/phone-otp *(Android, iOS, web)*
- **Multi-device:** up to `min(3, tenant device quota)` devices at once, set by the scenario's device-count setting. Auto resolves to one device per bound persona (minimum one), so a sequential multi-persona scenario pins an explicit count of 1. The count is decoupled from personas — two devices on one persona for session-conflict tests, or one device and two personas by signing in and out. This is what makes real-time cross-account behaviour assertable. Every device runs the same OS and the same app. Mini names each device by the role it gives it during the run ("Parent device", "Receiver"), and renames it when that role changes, so the run page and the report read by role rather than by index. *(Android, iOS)*

**What Mini cannot do — never write criteria that require:**

- Database, server-log or analytics verification — the evidence is what the app shows. *(Android, iOS, web)* **web:** The page's own API requests and responses are readable (see API request inspection). **Android:** The app's own API requests and responses are readable (see API request inspection). **iOS:** The app's own API requests and responses are readable (see API request inspection).
- Read email outside `@qa.minitap.ai` inboxes. *(Android, iOS, web)*
- Receive a real SMS or phone call — Minitap owns no phone number, so any OTP that can only arrive by SMS is untestable unless the persona carries a static code (see the phone-OTP capability above). *(Android, iOS, web)*
- Biometric auth (fingerprint, Face ID), NFC, or Bluetooth pairing. *(Android, iOS)* **iOS:** Hardware buttons beyond home are also out of reach.
- Hear or transcribe sound the device plays — audio output is not captured on mobile (web runs can). *(Android, iOS)*
- Toggle connectivity or airplane mode. *(iOS)*
- Rotate the viewport or mock a location — the web runner exposes no resize and no coordinate-override command, and the viewport is fixed to the preset the session starts with, so pick the right viewport preset up front. Granting the browser the geolocation permission is possible; choosing what it reports back is not. *(web)*
- Pair with a smartwatch, wearable or other external hardware (a second phone or tablet IS supported). *(Android, iOS, web)*
- Enter a real payment card or make a real-money purchase. Sandbox and test cards, in-app purchases and subscriptions through the RevenueCat Test Store or an Apple/Google platform sandbox, and an app's own custom payment flow are all testable, so this limits the money-moving step alone and not checkout as a feature. Write these criteria only against the test payment method the app actually provides — naming which one, since a Test Store build mocks billing while a platform sandbox drives the real store flow — and stop before the charge when no supported test payment method is available. *(Android, iOS, web)*
- Control or guarantee precise timing or gesture velocity ("tap within 200ms", "flick fast enough to fling the list") — action timing and gesture pacing are approximate, even when Mini can retrospectively observe the resulting transient state. *(Android, iOS, web)* **Android:** Pacing is noticeably slower than requested.

## Device count

A scenario's **device count** decides how many devices one run drives at once (Android and iOS only — web runs use one browser). A scenario stored without an explicit count uses **auto**: one device per bound persona, minimum one — a story binding zero or one persona runs on a single device, a story binding several personas gets one device per persona at run time. An explicit integer overrides auto in either direction. Both are capped at `min(3, the tenant's device quota, the app's device-concurrency limit)` — a story binding more personas than that cap runs on the cap. Omitting the field when *creating* a story leaves it on auto; on *updates*, omission leaves the current value unchanged — how to set or reset it is documented on each create/update call. The count is decoupled from the personas the story binds — see "Personas vs. devices" in the personas guidance.

**Extra devices are only for simultaneity.** Go above one device **only** for flows that verify **real-time cross-account or cross-device behavior**: live chat or a call between two users, a push or notification one account triggers for another, presence/typing indicators, or cross-account visibility (A blocks B, and B can no longer see A). A journey where one identity acts and another checks the result **sequentially** does not need extra devices — the tester signs in and out on one. Because auto gives a multi-persona story one device per persona, **explicitly set the device count to 1 on every sequential multi-persona story**; never rely on auto to "cover more personas". Most multi-persona suites still run one device per story.

Multi-device is the deliberate exception, not a default to reach for. For an ordinary app with no simultaneous-identity flow the correct counts are: **unset on single-persona stories** (auto already means one device) and **an explicit 1 on multi-persona ones** — anything higher changes cost and behavior for nothing.


## Offline and connectivity

**Cover offline and connectivity scenarios when the app warrants it.** If the app shows offline support, cached content, or sync mechanisms, create dedicated stories to test those flows. Example criterion: "Go offline (airplane mode), confirm the app shows cached content, then go back online and verify data syncs."

- On Android, name the transition the criterion needs: **"Offline (airplane mode)"** for a fully offline device, **"Wi-Fi off"** only when the app must react to losing Wi-Fi specifically. The tester restores connectivity before it reports.
- On web, the tester takes the page offline and back online, so word it as **"Offline"** rather than "Wi-Fi off" or "airplane mode".
- **iOS** runs cannot change connectivity — do not write network-toggle criteria for iOS; such a scenario is screened as a capability gap there.


## Test files

**Bind a test file to every story that picks one.** Test devices start with empty storage: an Android device has no photos, videos, documents or audio at all, and an iOS simulator has only a few stock photos, never the file the story needs. So whenever a story picks something from the device — a photo or video from the gallery, a document from the file picker, an audio clip, anything it attaches, uploads or imports — bind a test file of that kind when you create the story. Do not open the picker first to check: it is always empty until a file is bound.

- **Generic file** (any photo, a sample PDF, a short audio clip): bind one yourself. Reuse a test file the app already has when it fits; otherwise upload a stock one, then bind it. Never ask the customer for a generic file.
- **Specific real-world file** (an ID document, a real invoice, a printed QR code the app must recognise): only the customer has it. Ask them for it, and bind it once they upload it.
- Binding replaces the story's whole file set: pass every file the story should keep, not only the new one.
- Bound files are pushed to the device before each run, so the story can simply say "Choose the test photo from the library" — never describe how the file gets onto the device.


## Tags

**Tags** are labels on scenarios, shared by every app of the tenant. The UI groups and filters scenarios by tag, and a tag's description is shown to the tester on every scenario carrying it — so tags affect runs, not just grouping.

1. **List the existing tags first** (`minitest tags list`) and reuse them. Match case-insensitively: never create `checkout` next to an existing `Checkout`.
2. **Give each scenario 1–3 generic tags** naming its feature area or team (`Checkout`, `Auth`, `Search`, `Onboarding`, `Payments`). A tag is meant to group many scenarios, so **never use the scenario's title as a tag**.
3. **Create a tag only when nothing existing fits**: `minitest tags create --name <name> [--color <color>] [--description "<what the tester should know>"]`, or pass `--tag <name>` (repeatable) to `minitest scenario create` / `update` — unknown names are created. On `update`, any `--tag` replaces the scenario's whole tag set.
4. Tag names are at most 40 characters and contain no comma.
5. There are **no flow types, story types or categories** anymore: never pass `--type`, never use `minitest flow-types`.


## Personas and the `@qa.minitap.ai` test-profile mechanics

The executor signs in and reads codes through Minitap's test-profile machinery.
The full persona doctrine below governs how you name profiles and, critically, how
the `@qa.minitap.ai` inbox, OTP, passwordless vs. provisioned accounts, and the
shared Google pool actually behave at runtime — design credentials and account
state to match.

A **test profile** (persona) represents one specific user identity and state. Stories bind profiles via a many-to-many relation: several profiles may be bound to one story, none is "primary" to the tester, and it picks whichever fits each step of the journey. (Dependency checks compare one of them: the alphabetically first bound profile.)

**Every story is bound to at least one persona.** If you create a story without binding a profile, the system binds the app's **default profile**; when the app has no default, it binds the app's **"New user" persona** (which then becomes the default). Updating a story with an empty profile list binds "New user". "New user" is system-managed and read-only — it cannot be edited, deleted, given credentials or a test card, or marked exclusive — and it represents a genuine brand-new user: the tester proceeds anonymously where the app allows it, and when the flow needs an identity it signs up with an address it makes up itself, `<random>@qa.minitap.ai`, and reads the code from that inbox. Use the "New user" persona deliberately for first-launch, guest-browsing, registration, and anonymous flows — do not create your own "anonymous" or "guest" profile for browsing, and do not treat sign-in as mandatory for it (many apps are usable anonymously). The exception is a persona that owns the address a record is made under, even when the app calls that user a guest — see "State only a commit makes" below.

**"New user" is for stories whose SUBJECT is being new — not for every story that happens to need an account.** First-run onboarding, registration, guest/anonymous browsing, and empty-state checks are what it is for: in each of those, "this account has no history" is the thing under test. A story that merely *requires* someone to be signed in — settings, profile, a stats screen, a feature behind the login wall — binds the cheapest **pre-existing** persona instead, and the difference is not stylistic:

- **It is the expensive choice, not the cheap one.** A pre-existing persona signs in (a few steps); "New user" re-walks the entire registration funnel — often fifteen-plus screens — before the story can assert anything, on every run, forever. That arrival is what exhausts a run's budget before it reaches a verdict.
- **It makes the story ungateable.** A persona that registers itself needs nothing before it, so it can have no parent. Bind a suite's feature stories to "New user" and its dependency graph cannot exist: there is no sign-in for anything to hang off, and a broken login shows up as N separate reds instead of one root cause and N-1 skips.

Measured: a mature 67-story suite binds 52 stories to one pre-existing account and only 12 to "New user" — the 12 being genuinely first-run journeys. A guided onboarding that inverted that ratio (7 of 11 on "New user") produced a suite with two dependency edges and no root, and every one of those seven stories opened by signing up from scratch. If most of your suite is bound to "New user", that is the defect to look at first.

**Proactively create every profile the app needs for thorough testing.** During discovery, identify all distinct user roles, subscription tiers, and permission levels. Each one that affects what the user sees or can do on screen deserves its own test profile. Common examples:

- Free vs. Premium/Pro users (different features, paywalls, limits)
- Different roles (Driver vs. Diner, Patient vs. Doctor, Admin vs. Member)
- Returning user with populated data (vs. the empty-state case, which is the system "New user" persona)

**Freemium and paywalls:** when the app has tiers, create one persona per tier and spell out the entitlements in each persona's `about` field (what this tier can and cannot do). Classify paywalls explicitly: a **hard paywall** blocks the feature entirely for a lower tier; a **soft paywall** shows an upsell that can be dismissed or bypassed. Record which is which (and how a free user gets past a soft wall) in the app knowledge, so the tester never guesses.

**Naming:** name profiles after the app's real personas — not generic labels. A food delivery app has "Driver" and "Diner", not "Standard user". A clinic app with a freemium model has "Patient", "Doctor", "Free User", "Pro User".

**Credentials:** generate a passwordless `@qa.minitap.ai` persona for each profile and leave the password blank. Use a descriptive prefix derived from the role plus the app name, e.g. for an app called "FoodDash": `minitest-free@qa.minitap.ai`, `minitest-driver@qa.minitap.ai`. Leaving the password blank makes the persona OTP-first: at runtime the tester registers/signs in with that `@qa.minitap.ai` address and reads the confirmation or one-time code straight from its inbox — no real backend account needed. **Never invent a password or use a non-`@qa.minitap.ai` domain for a generated persona** — a passwordless non-`qa` address is rejected at creation, and a non-readable inbox defeats OTP. Only set a username + password when the customer has a real account they own (any domain is then allowed). A passwordless persona created with a blank username gets a generated `<random>@qa.minitap.ai` address. The `@qa.minitap.ai` check runs only at creation, so never later swap in another domain or clear the password of a non-`qa` persona.

**Apps that sign in by phone** take a `phone_number` (E.164, e.g. `+14155551234`) instead of, or alongside, the address — plus a `static_otp_code` when the customer's backend accepts a fixed code for that number. Both must be pre-provisioned by the customer: ask them for a whitelisted number and its fixed code, because there is no phone inbox to read at runtime the way there is for `@qa.minitap.ai`. A persona that carries a phone number or a static OTP code has its own way in, so it keeps whatever address you give it — a real customer address is accepted, and no `@qa.minitap.ai` inbox is invented for it (a persona with a static OTP code but no phone and no username still gets a generated one).

**For a persona that needs a specific account state (e.g. premium/pro), generate a `<something>@qa.minitap.ai` persona *with* an explicit password and ask the user to add that email + password combo to their backend** so it is linked to a user in that state — the `qa` address keeps the inbox readable for OTP while the password lets them pre-provision the account. The `about` field must explain who this persona is and what state they need to be in (e.g. "Pro subscriber with an active monthly plan. Has completed onboarding and has at least one saved item.").

**Personas that pay** carry a `test_card`: a sandbox payment card (number, expiry, CVC, holder name, postal code — every field optional, trimmed and otherwise stored as typed; the number allows only digits, spaces and dashes) that the customer's payment provider accepts in test mode, stored encrypted like a password. Set it on the persona that runs the checkout scenarios with `minitest test-profile create|update --test-card-number … --test-card-expiry … --test-card-cvc … [--test-card-holder-name …] [--test-card-postal-code …]`; `update` merges into the stored card and `--clear-test-card` removes it. Where the card comes from:

- **First, Stripe's public test card** (`4242 4242 4242 4242`, `12/34`, `123`) is tried without asking the customer, on any Stripe checkout or one whose provider is unknown (every native app included) — unless the page shows live mode (a `pk_live_` key), where a test card is always declined.
- **If it is refused**, or the checkout is live or another named provider, ask the customer which test card their staging checkout accepts.

Never invent any other card, and never put one in `about`. A card lets the agent fill the payment form; whether it completes the payment is still governed by its own rules.

**For "Sign in with Google", bind no Google credentials and create no profile for it.** Pooled Google accounts are not personas: whenever a criterion needs Google sign-in, the tester leases one from Minitap's shared pool at runtime and fetches its password and 2FA code on demand — none of this is in the prompt, so static credentials would be wrong and unusable. A leased account may already carry data from a previous run, so the tester resets it to a clean starting state before the scenario.

**State must match the scenario.** A story must link a profile whose state actually matches its scenario. Do not bind a generic profile whose state contradicts the story (e.g. an active subscriber on a "lapsed subscriber" story). When no existing profile matches the required state, create a dedicated one and describe that state plainly in its `about` field.

**State only a commit makes.** Some journeys start from a record only a commit creates — an active booking to manage, a placed order to track. When the customer allows that commit in their test environment, a producer story makes it and the stories that read it depend on it (see dependencies). Give that chain a persona whose `@qa.minitap.ai` address owns the record, even when the app has no accounts and that user is a "guest" in the app's words — it is an address the record lives under, not a browsing profile. Its `about` says where the record's data arrives:

- ✅ `minitest-booker@qa.minitap.ai`, about: "Makes and manages bookings. Confirmation numbers and lookup codes arrive in this inbox; use the newest."
- ❌ Asking the customer for an active booking, its confirmation email, or "an email that has never signed up".

Any email field an app asks for takes a `@qa.minitap.ai` address, and a contact phone field nothing is sent to takes a number reserved for fiction (UK `+44 7700 900123`) — only a number that must receive a code is the customer's to provide. When a phone field already shows or has selected a country code (a flag, a `+44` prefix, a country picker), type only the national number and check what the field now shows. A value the form rejects is a field-entry problem: clear it fully and enter it another way (the national digits, the country picked from its picker, the number typed key by key). A value you typed yourself, or data on an account this run created, is never the customer's account to fix. A flow that needs an address nobody has used before runs as "New user", which gets a fresh one every run; a fixed address is spent by its first run. "New user" cannot hold a test card, so when that flow also pays, create a persona that holds the card and whose `about` says: "Sign up with a fresh `<prefix>-<random>@qa.minitap.ai` every run; never reuse this address."

**Personas vs. devices.** A persona is an *identity*; a device is a *surface*, and the two are decoupled — a scenario's device count is set independently of how many personas it binds (see "Device count" below). Bind the personas the journey needs, then decide the device count from *how* those identities are used:

- **Simultaneous identities → multiple devices.** When two identities must be live *at the same time* — real-time chat or a call between two users, a background push one account triggers for another, presence/typing indicators, or cross-account visibility (A blocks B, and B can no longer see A) — each concurrent identity needs its own device so the tester can observe both screens at once.
- **Sequential identities → one device.** When the journey uses identities one after another — post as A, then sign out and check as B — a single device is enough; the tester signs in and out. Binding two personas does **not** by itself require two devices — but because the auto default resolves to one device per bound persona, set an explicit `device_count` of 1 on these stories.
- **Same account twice → two devices, one persona.** A session-conflict test (the same account signed in on two devices) binds a single persona but runs on two devices.

**Constraints:**

- **Names** are unique per app (case-insensitive), at most 255 characters. Username and password ≤255, `about` ≤2000, `static_otp_code` ≤32, `phone_number` is E.164.
- **Deleting** a profile still bound to a story is refused (409); unbind it first.
- **Shared profiles** can be bound but are read-only: they cannot be edited, deleted, or set as default.
- **`exclusive_use`** keeps two concurrently running tests off the same account — matched by login (username, else phone number), so it also covers the same login bound as a persona in another app. Set it on every persona that signs into that account: a non-exclusive persona on the same login is not held back (API only; minitest-cli has no flag for it).
- **Status:** each persona has a provisioning status (`untested`, `unverified`, `working`, `failed`). Editing a credential resets it; only a real sign-in sets `working` or `failed`.

**Coverage check:** before story creation, verify you have a profile for every distinct persona visible in the app. Missing a profile means missing entire feature surfaces.

**Default profile rule:** set a default profile only when a single persona is clearly the one most newly created stories should start with (typically the main signed-in account). If multiple personas are equally primary, leave default unset.

