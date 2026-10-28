<!-- rendered by Minitap — do not edit -->
# Suite Schema & Step-Writing Rules

`suite.yaml` is a **local artifact** you iterate on in the temp working dir. It is
not persisted anywhere by Minitest — it is the design you review, harden, and then
replay through the `minitest` CLI in Wave 6. The intermediate artifacts
(`00-recon.md` … `04-state-model.md`) are plain markdown with `file:line` evidence
on every factual claim; only the persona catalog and `suite.yaml` are YAML.

## suite.yaml

```yaml
app: <name>
generated: <ISO date>
source_commit: <git sha of the analyzed codebase>

personas: []   # the 03-personas.yaml entries actually used by a scenario

scenarios:
  # Gate scenarios: one per persona that must be established (onboarded /
  # signed in) before feature scenarios can run. A gate STARTS from a fresh app
  # launch and ENDS signed in / onboarded as its persona. Every feature scenario
  # depends on its persona's gate: if the gate fails, dependents are skipped.
  - id: gate-signin-premium-seeded
    kind: gate                          # gate | feature
    name: "Sign in as the premium seeded account"
    tags: [Auth]                        # 1–3 generic feature-area tags (see minitest-target.md)
    personas: [premium-seeded]          # the persona(s) this scenario binds — a
                                        # gate ESTABLISHES exactly one, so a 1-element list
    depends_on: []
    dependency_rationale: null          # gate roots need none
    assumptions: []
    steps:                              # design aid — folded into the description at apply time
      - "Launch the app; the Welcome screen appears"
      - "Tap 'Log in'"
      - "Type the premium test account email into the 'Email' field"
      - "Type its password into the 'Password' field"
      - "Tap 'Log in' and wait for the loading indicator to finish"
    acceptance_criteria:
      - "The Home screen is displayed"
      - "The premium badge is visible next to the profile avatar"

  - id: checkout-saved-card
    kind: feature
    name: "Checkout with a saved card"
    tags: [Checkout]
    personas: [premium-seeded]          # account(s) expected connected at start
    depends_on: [gate-signin-premium-seeded]
    dependency_rationale: >
      Gate: requires the premium-seeded session. A NON-gate edge must instead
      cite the state-model fact — what the parent produces that this consumes,
      and why it is expensive/irreversible.
    assumptions: []                     # e.g. 'remote flag new_checkout=on (common variant)'
    steps:                              # human-reproducible, one atomic action each
      - "From the Home tab, tap the search icon in the top bar"
      - "Type 'wireless mouse' in the search field"
      - "Tap the first result to open its product page"
      - "Tap 'Add to cart'"
      - "Tap the cart icon in the top-right corner"
      - "Tap 'Pay' and wait for the processing indicator to finish"
    acceptance_criteria:                # visually verifiable, one check each, ordered
      - "The cart screen lists the added item with its price"
      - "An order confirmation screen with an order number is displayed"

  # Multi-persona scenario: ONE collaborative story that binds several personas
  # at once — for a flow that spans two accounts live in the same session (a
  # driver + a diner, two chat participants, an admin + a member). This is the
  # collaborative-journey case: the personas are co-actors in a single story, NOT
  # two different-persona stories wired by a dependency edge (a dependency edge
  # still requires a shared persona — see the persona-continuity invariant below).
  # Two simultaneous identities → two devices (set device count accordingly).
  - id: order-handoff-driver-diner
    kind: feature
    name: "Diner places an order, driver accepts and delivers it"
    tags: [Orders, Delivery]
    personas: [diner-seeded, driver-seeded]   # both co-actors of this one story
    depends_on: []                      # gates for each persona go here if they have one
    dependency_rationale: null
    assumptions: []
    steps:                              # one device per live identity; label whose screen
      - "On the diner's device, from the Home tab tap 'Order again' on the last restaurant"
      - "Tap 'Place order' and wait for the confirmation screen"
      - "On the driver's device, wait for the new delivery request to appear"
      - "Tap 'Accept' on the delivery request"
      - "Tap 'Mark as delivered' once the route completes"
    acceptance_criteria:
      - "The diner's device shows the order status change to 'Delivered'"
      - "The driver's device shows the delivery moved to the completed list"
```

## Why `steps` live in the local YAML but not in the minitest story

Writing out **human-reproducible steps** while you design forces the scenario to
be real: a stranger could execute it, which surfaces missing setup, hidden
interstitials, and unreachable screens before a single run. That design value is
why `steps` stay in `suite.yaml`.

Minitest stories persist **no** `steps` field. At apply time (Wave 6) you fold the
step sequence into the story **description** as the big UX path plus the
feature/product-area anchor — the shape the acceptance-criteria doctrine expects:
a path, not choreography, that tells Mini the intent and the route to the tested
state without micro-managing every tap. The `acceptance_criteria` transfer
one-to-one to `--criteria`.

## Where assumptions resolve

Each entry in a scenario's `assumptions` resolves to one of two homes when you
apply — never to a `suite.yaml`-only note:

- **App-level** (a paywall's hard/soft nature, a remote flag's common variant, a
  provisioning fact true across the app) → an `app-knowledge update`.
- **Scenario-local** (a precondition or variant specific to one story) → that
  story's **description**.

### Step-writing rules (human-reproducible)

Steps must be executable as-is by someone who has never seen the app:

- **One atomic action per step** ("Tap X", "Type Y in Z") — never a compressed
  goal ("get a book to its final segment").
- **Explicit anchor**: the first step states the starting point (fresh launch, a
  given tab). Combined with the gate, the full path from app start is unambiguous.
- **Concrete data**: spell out values to type ("type 'dune'", "enter a unique
  email like qa+<timestamp>@test.com") — never "enter a query".
- **Exact on-screen labels**, quoted, in the app's locale (from the strings
  files), with a translation in parentheses when helpful.
- **Waits/dialogs included**: OS permission dialogs, loading indicators, and
  interstitials (paywalls, rating prompts) each get their own step with the
  action to take.
- **Inlined setup is written out in full** — cheap state the story needs is set
  up step by step, never summarized.
- Soft cap ~15 steps; if a scenario needs more, its setup is probably an
  irreducible state that belongs to a dependency.

### Invariants (checked in Wave 5)

- `depends_on` graph is acyclic; depth ≤ 3 counting only non-gate edges.
- **Persona continuity**: a dependency edge B→A stays within one identity — A and B
  must share the persona whose established state the edge reuses (the backend
  rejects a cross-persona edge with `422 persona_mismatch`). A scenario that binds
  *multiple* personas is a single collaborative story with co-actors, not a
  dependency edge between two different-persona stories — never wire a cross-persona
  dependency edge to fake collaboration; bind the co-actors on one story instead.
- **Gate coverage**: every feature scenario depends on the gate of each of its
  personas that has one; every persona requiring establishment has exactly one gate
  scenario.
- **Non-gate edges cite a state-model fact**: A produces the state B consumes, and
  that state is expensive/irreversible (cheap setup is inlined instead).
- **No dependency on auth-changers**: no scenario depends on a non-gate scenario
  whose auth trajectory ≠ none (sign-out, account switch/create/delete end states
  are asserted in their own acceptance criteria; they are terminal nodes).
- Every persona in the top-level `personas` list is used by ≥ 1 scenario; every id
  in a scenario's `personas` list is defined in that top-level `personas`.
- Every capability-matrix row is covered by ≥ 1 scenario.
- Every step is atomic and human-reproducible per the rules above.
- No acceptance criterion mentions backend, database, network, or any non-visible
  effect.
