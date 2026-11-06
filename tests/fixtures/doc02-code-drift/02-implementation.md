# Implementation

## Equal block

`src/worker.ts`

```ts
export function helper(x: number) {
  const doubled = x * 2
  return doubled + 1
}
```

## Stale block (the real case: `finally` without the guard)

```ts title=src/worker.ts
export async function run(job: Job) {
  const lock = await acquire(job.id)
  try {
    await job.exec()
  } catch (err) {
    log(err)
  } finally {
    await lock.release()
  }
}
```

## Pre-change state, marked

antes: `src/worker.ts`

```ts
export async function run(job: Job) {
  try {
    await job.exec()
  } finally {
    await lock.release()
  }
}
```

## A diff

`src/worker.ts`

```diff
-    await lock.release()
+    if (lock.held) {
+      await lock.release()
+    }
```

## Comments and elision still match

`src/worker.ts`

```ts
// paste-ready, trimmed
export async function run(job: Job) {
  const lock = await acquire(job.id)
  ...
  } finally {
    /* only release what we hold */
    if (lock.held) {
      await lock.release()
    }
  }
}
```

## Too short to judge

`src/worker.ts`

```ts
const nothing = 0
return gone
```

## Two files on the line above: ambiguous, skipped

Compare `src/worker.ts` with `src/other.ts`.

```ts
completely different()
code.that.matches(nothing)
```
