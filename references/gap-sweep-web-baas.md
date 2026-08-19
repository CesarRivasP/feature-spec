# Gap sweep layer — web app on a BaaS backend

Applies when `_profile.yml gap_sweep_layers:` includes `web-baas`. Runs **after** the base sweep in `gap-sweep.md`, never instead of it.

## New endpoint / webhook receiver
- **Who authenticates it?** If JWT verification is off, name the mechanism that replaces it (signature, shared secret, IP allowlist). "It's an internal URL" is not a mechanism.
- **Validated before parsing?** Signature checks run on the raw body, before deserialization.
- **Replay/redelivery?** Senders retry on timeout. Same event arriving twice must not double-write or double-alert.
- **Unknown event types?** Ignore + 2xx, never crash, never insert.
- **Failure contract stated?** Exact status per failure (missing header, bad signature, unknown type, internal error) — matching a sibling endpoint already in the repo if one exists.
- **Status matches permanence, not just presence.** A known event type with an incomplete payload (missing a field a `NOT NULL` column needs) is a *permanent* failure — retrying the identical payload fails identically forever. That must return 4xx (dropped, visible in the sender's dashboard as a permanent failure), never 5xx (sender retries, same failure, forever). Any error branch derived from the payload's *content* — as opposed to infra/DB availability — gets this question asked explicitly.

## New table (on top of the base sweep's "new persisted data")
- **RLS stated explicitly?** Default-deny plus the one role that writes. "We'll add RLS" is not a spec.
- **Service-role key reachable from the client?** Name which side holds it. A key that ships in a bundle is public.
- **Does the migration hold under concurrent writes?** A backfill plus a `NOT NULL` added in the same migration fails on rows inserted between the two statements.

## Edge function / serverless
- **Cold-start budget vs the caller's timeout.** If the platform's gateway cuts at N seconds, any work over N must be queued, not awaited. Name the numbers — both of them — in `limits.*`.
- **Does it fan out to another provider?** Then the whole "third-party API" section of the base sweep applies to the inner call too, and its rate limit is shared across every concurrent invocation.

## Verifying this layer
Provider config that produces no error when wrong (auth redirect allowlists, storage bucket policies, default regions) cannot be checked by reading code. The doc must state which of these are verified by **executing the flow against the real project**, and that step is `[MANUAL]`.
