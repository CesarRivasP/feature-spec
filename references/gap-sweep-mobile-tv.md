# Gap sweep layer — TV / D-pad apps (Android TV, Fire TV, Apple TV, tvOS)

Applies when `_profile.yml gap_sweep_layers:` includes `mobile-tv`. Runs **after** the base sweep in `gap-sweep.md`. On Android TV, run the `android-native` layer too — this one only adds what the remote and the hardware change.

## New or modified focusable UI
- **Is there a focusable view on screen at all times?** A screen whose only focusable element unmounts (empty list, loading state, error state) leaves the D-pad dead — the user cannot navigate out and force-kills the app. Every state of the screen, including empty and error, names its focus host.
- **Where does focus land on entry, and on return?** Both. Return-from-detail is the case that breaks: the list may have shrunk, the index may no longer exist, and the restored index may be clamped somewhere the user did not leave from.
- **Each of the four directions has a stated destination.** Including the edges. "Up from the first row" is a real case with a real answer, not an implicit no-op.
- **BACK is specified separately from every other key.** It is the one key with system-level meaning; a screen that consumes it without saying so traps the user.

## Anything asserted about focus
- **Focus claims are behavioral claims.** "Autofocus grabs the first focusable" / "the ring lands on the grid" is `basis: measured, how: device`, or it is `basis: asserted` with a `falsified_by:`. There is no third option. Native focus and the visual highlight can diverge with no error, so a screenshot is not proof of where focus *is*.
- **A diagnostic log line names its emitter.** Two rows both printing `row=0` are indistinguishable in the log. See `references/implementable.md` §Diagnostic log lines.

## Low-end / 32-bit devices
- **Memory ceiling.** Fire TV sticks and older Android TV boxes are 32-bit with a small per-process heap. Anything that buffers a whole response, decodes a full-size image, or caches pages of a list needs a stated bound — and the verification runs on the *worst* device in the matrix, named in the spec.
- **Which devices is this verified on?** A TV feature verified only on an emulator is `basis: asserted` for every real device. Name the device in `evidence`.

## Playback and lifecycle
- **Backgrounding during playback.** Pausing versus tearing down the surface is a decision with an ANR on the wrong side of it. State which one, and where.
- **Long-press / key-repeat.** Holding a direction emits a stream of events. Anything that fires a network call or a seek per key event needs a debounce, a coalescing step, or a stated reason it is safe.

## Verifying this layer
Device procedures come from `_profile.yml commands.force_stop` / `commands.device_log`. A focus procedure is numbered, ends in an observation ("which element carries the focus ring"), and — because focus can be visually right and natively wrong — prefers a log line over the eye where one exists.
