# Gap sweep layer — native Android

Applies when `_profile.yml gap_sweep_layers:` includes `android-native`. Runs **after** the base sweep in `gap-sweep.md`, never instead of it.

## New or modified manifest component (Activity, Service, Receiver, Provider)
- **`android:exported` stated explicitly?** Since API 31 it must be. Say the value and why. `exported="true"` with no permission is a public entry point into the app — any installed app can start it with any extras.
- **Are the extras trusted?** Anything arriving via `Intent` from outside the app is untrusted input (base sweep §Untrusted text). Name what validates each extra it reads. A cast that assumes a type crashes the app from a third-party `am start`.
- **`PendingIntent` mutability?** `FLAG_IMMUTABLE` unless the spec states why it must be mutable.
- **Launch mode / task affinity changed?** Say what re-entering the app from a notification or recents now does — a `singleTask` change silently rewrites back-stack behavior for every entry point, not just the new one.

## New deep link / app link
- **Host and scheme validated?** An intent filter matching `scheme="https"` with no host verification is claimed by any link.
- **What renders on a malformed or hostile link?** Enumerate: unknown path, missing id, id belonging to another user. Each maps to a visible state.
- **Does the link bypass auth?** If the target screen assumes a logged-in session that a deep-link entry does not guarantee, say where the check happens.

## New runtime permission
- **Denied — and denied permanently — are two different branches.** Both need a UI state; "don't ask again" cannot be recovered in-app, so the spec names the settings-deep-link path or states that the feature is unavailable.
- **What does the feature do without it?** Degraded mode or hard block. Not "it won't work".
- **Foreground-service type declared?** Since API 34 the type is required and must match the permission.

## Background work
- **Doze / App Standby / OEM killers.** Anything scheduled must state which mechanism it uses (`WorkManager`, alarm, JobScheduler) and what its latency actually is when the device is idle. "It runs every 15 minutes" is false on a dozing device and on most OEM builds.
- **Process death mid-flow.** The system kills the process between two screens. State what is restored from `SavedStateHandle`/persisted state and what is simply lost.
- **Is it exempt-dependent?** If it only works with battery-optimization disabled, that is a `[MANUAL]` user step, not an implementation detail.

## Build / release configuration
- **R8 / ProGuard.** Anything reached by reflection, any `Serializable`/Gson/Moshi model, any JNI entry point needs a keep rule named in the spec. This class of break appears only in release builds — the spec must say the verification runs on a **release** build, or the phase's `Verificación` is testing the wrong artifact.
- **New dependency.** Method count, minSdk floor, and transitive permissions it adds to the merged manifest. A library that quietly merges `ACCESS_FINE_LOCATION` changes the store listing.
- **minSdk-guarded API.** Every API above minSdk needs its else-branch specified, not just a `@RequiresApi`.

## Local persistence (on top of the base sweep's "new persisted data")
- **Room migration written, not `fallbackToDestructiveMigration()`.** If destructive is genuinely intended, that is a stated accepted risk with the data it discards named.
- **Access control on this stack means**: file permissions and process boundary. Data in `getExternalFilesDir`, in a `SharedPreferences` file, or in an unencrypted DB is readable on a rooted device and by anything with the right `content://` grant. If it holds a token or PII, name the encryption (`EncryptedSharedPreferences`, Keystore-wrapped key) or accept the risk explicitly.
- **`allowBackup`.** Default `true` means the data leaves the device via cloud backup. State the value for anything sensitive.

## Verifying this layer
- Instrumentation and observation come from `_profile.yml commands.device_log` / `commands.force_stop`, not from hand-typed `adb` lines.
- A behavioral claim here is `basis: measured, how: device` with a numbered procedure — see `references/evidence.md`. Reasoning about lifecycle from source alone is `basis: asserted` and must say so.
