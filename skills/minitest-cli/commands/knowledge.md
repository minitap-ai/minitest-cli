# Knowledge v2 (`minitest brief`, `app-guide`, `glossary`, `knowledge`)

On workspaces with **Knowledge v2**, what Mini knows about an app is no longer
one app-knowledge document. It is split into elements, each with one job, an
author on every change, and a history you can read. Write each fact in the one
element whose job it is.

| Element | Its job | Limit |
| --- | --- | --- |
| **Product brief** | The app's identity card: what the product is, who uses it, its domain and what matters most to its users. It frames every other piece of writing about the app, so keep it stable and factual. No navigation steps, no test data, no judging rules. | 2000 chars |
| **App guide** | How to get around the app: main screens and navigation, roles, interactions a newcomer would miss, the paywall map, feature-flag caveats, how test accounts and payments work. The tester reads it on every run, so it orients rather than specifies. | 30000 chars |
| **Glossary** | The app's own names for its screens, objects, roles and actions: one entry per term, its meaning in this app and optional aliases. Reports and criteria use these terms verbatim. | one entry per term |
| **App skills** | How to put the app into a state a test needs (a test backend call, a debug menu, a sandbox payment). See [`app-skills.md`](app-skills.md). | |

Where a fact goes:

- "The app is a language-learning app for adults" → **brief**.
- "The Profile tab is behind the avatar; long-press a lesson to restart it" → **app guide**.
- "A *Pod* is a group of up to five learners" → **glossary** (not a `## Glossary` section in the guide).
- "Call `POST /test/reset-user` to start from an empty account" → **app skill**.
- How to judge a result ("a 2-second spinner on checkout is expected on staging") → a **judgment rule**, created when the customer marks a verdict **Not a bug** in the webapp. Judgment rules have no CLI.
- What one scenario must do and check → that scenario's steps and acceptance criteria, never the knowledge elements.

Never copy a fact into two elements. When a fact fits none of them, leave it
out rather than forcing it into the nearest one.

## Commands

All of them are app-scoped: the global `--app` goes before the subcommand.

```bash
# Product brief and App guide: same shape
minitest --json --app <app_id> brief get          # {content, versionNumber, actor:{kind,id,channel}, createdAt}
minitest --json --app <app_id> brief update --content "Language-learning app for adults…"
minitest --json --app <app_id> app-guide update --content-file ./app-guide.md
minitest --json --app <app_id> app-guide get

# Glossary: address a term by id or by the term itself (case-insensitive)
minitest --json --app <app_id> glossary list      # {terms:[{id, term, meaning, aliases, sourceRef, actor, updatedAt}]}
minitest --json --app <app_id> glossary add --term "Pod" --meaning "A group of up to five learners" --alias squad
minitest --json --app <app_id> glossary update Pod --meaning "A group of up to five members"
minitest --json --app <app_id> glossary update Pod --alias squad --alias team   # replaces the aliases
minitest --json --app <app_id> glossary update Pod --clear-aliases
minitest --json --app <app_id> glossary remove Pod --yes

# Who changed what, newest first
minitest --json --app <app_id> knowledge history
minitest --json --app <app_id> knowledge history --element glossary --limit 50

# Undo: restore an element to a version listed by history
minitest --json --app <app_id> knowledge revert <versionId>
```

`update` on brief / app guide replaces the whole content and creates a new
version; read it first and edit the result. Without `--json`, `update` prints
the new version number on stdout. `knowledge history` returns
`[{versionId, element, versionNumber?, termId?, change, actor, conversationId, causeRef, createdAt, before, after}]`;
`change` is `created`, `updated`, `deleted` or `reverted`. `knowledge revert
<versionId>` puts the element (a document, or one glossary term) back to that
version's content and records it as a new `reverted` change, so it can itself be
reverted. Every write from the CLI is recorded with channel `cli` by default;
set `MINITEST_CHANNEL` to tag an automated editor's writes with another channel.

## Workspaces without Knowledge v2

Writes exit 1 with `Knowledge v2 (Product brief, App guide, Glossary) is not
enabled for this workspace`. Keep using `minitest app-knowledge` there.

On a v2 workspace the reverse holds: `app-knowledge get` still works and returns
a document rendered from the brief, app guide and glossary, but `app-knowledge
update` is refused — `PUT /api/v1/apps/{app_id}/app-knowledge` answers HTTP 409
with a flat `{error, message}` body, error code `knowledge_v2_enabled` and the
message "This workspace uses typed knowledge: edit the Product brief, App guide
or Glossary instead of the App knowledge document." The CLI prints that as
`Validation error (409): <backend message>` and exits 1. Edit the elements with
the commands above, not that rendered document.
