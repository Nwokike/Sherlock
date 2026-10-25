# Audit: src/screens/onboarding_screen.py

## 1) File role

First-launch 3-slide onboarding component (`@ft.component`, 286 lines). Renders a gradient backdrop, a tappable dot indicator, swipeable slide body, Skip/Next/Get Started CTAs, and persists completion via `ControllerMethods.set_onboarding_done` (or a `StorageService` fallback). Shown by `app_shell.py` when `_should_show_onboarding(state)` is true (lines 736/771/911). Mutates `AppState.is_first_launch`/`has_accepted_terms`.

## 2) API verification

All flet names used in this file exist in the installed 1.0.4 package and were signature-checked:

- Controls/enums: `ft.component`, `ft.use_context`, `ft.use_state`, `ft.Container`, `ft.Column`, `ft.Row`, `ft.Text`, `ft.Image`, `ft.Icon`, `ft.FilledButton`, `ft.TextButton`, `ft.GestureDetector`, `ft.LinearGradient` (lines 57-286) — all present.
- `ft.Animation(tokens.ANIM_SLOW, ft.AnimationCurve.EASE_OUT)` (line 176) — valid positional dataclass construction (`duration`, `curve`).
- `ft.Padding(left, top, right, bottom)` positional order matches field order (lines 202, 230, 237).
- `ft.DragEndEvent.primary_velocity` (line 153) — field exists.
- `ft.Icons.ALTERNATE_EMAIL_ROUNDED`, `DOWNLOAD_ROUNDED`, `CHECK_ROUNDED`, `ARROW_FORWARD_ROUNDED` (lines 35, 45, 259, 261) — present.
- `ft.Colors`: `PRIMARY` absent (uses `AppColors.PRIMARY` string), `SURFACE`, `ON_SURFACE`, `ON_SURFACE_VARIANT`, `WHITE` (lines 64, 67, 88, 95, 173, 175, 191, 213, 257, 276) — present. `AppColors.ACCENT` is a string (`#0EA5E9`), used at line 36/71 — fine.
- Tokens referenced (`ICON_FEATURE`, `SPACE_*`, `FONT_*`, `RADIUS_XL`, `OPACITY_LIGHT`, `OPACITY_MUTED`, `ANIM_SLOW`) all exist in `core/tokens.py`.
- `ft.Image(..., color=...)` (line 60) valid; blend mode defaults to None, so the tint only visibly applies on dark mode — cosmetic, not a crash.
- No use of `PageView` or `AnimatedSwitcher` in this file; slides are swapped manually by index. No hallucinated control names found.

## 3) Flow logic

- Slide index state `page_idx` (line 113); `is_last` (line 115).
- Next: if last, `_finish()`; else `set_page_idx(page_idx + 1)` (lines 141-146).
- Skip always `_finish()` (lines 148-150).
- Swipe: velocity thresholds +/-200, clamped (lines 152-159).
- Dots: tappable, set index (lines 161-163, 178-183).
- Completion persistence: prefers `controller.set_onboarding_done` (always truthy default `_noop_async`), fallback `StorageService(page).set(STORAGE_ONBOARDING_DONE, "true") + flush()` (lines 117-131). Then sets `state.has_accepted_terms = True`, `state.is_first_launch = False` (lines 132-133).
- Round-trip: `main.py` reads `storage.get(STORAGE_ONBOARDING_DONE) == "true"` on load and sets the same two flags (main.py:844-847); `set_onboarding_done` writes+flushes (main.py:1881-1889). Flag round-trips correctly when the controller path runs.

## 4) Bugs (severity-ordered)

1. **Dead fallback branch (medium).** `if controller.set_onboarding_done:` (line 122) is always truthy because `ControllerMethods.set_onboarding_done` defaults to `_noop_async` (controller_ctx.py:65), so the `else` StorageService path (lines 125-129) can never execute. The fallback is effectively dead code; if the controller is mis-wired, onboarding completes in memory but is never persisted.
2. **Persistence failure masked (medium).** `_finish` swallows all exceptions (`except Exception: pass`, line 130) yet still flips `state.has_accepted_terms`/`is_first_launch` (lines 132-133). A failed flush leaves storage stale, so onboarding reappears next launch while the in-memory app thinks it is done.
3. **No re-entrancy guard (low).** `_on_next` on the last slide and `_on_skip` both `spawn(_finish())` (lines 144, 150); rapid double-tap can run two concurrent finishes, double-writing storage and racing state updates.
4. **Unused `page` binding (low).** `page = context.page` (line 120) is only used by the unreachable fallback; dead-ish.
5. **Stale-closure risk on rapid input (low).** `_on_next`/`_on_swipe` read `page_idx`/`is_last` from the render in which they were created (lines 115, 141-159). Rapid clicks before a re-render could apply stale increments; flet usually re-binds, but there is no functional update (`set_page_idx(prev => ...)`).
6. **Haptic construction may be unmounted (low).** `_buzz` calls `spawn(shared_haptics().light_impact())` (line 139) with no page arg; `shared_haptics()` resolves `flet.context.page` and falls back to inline `ft.HapticFeedback()` when absent, whose `light_impact()` coroutine then fails at invoke time (logged, not crashed).

## 5) Improvements

- Remove or actually wire the dead `else` branch; rely on `controller.set_onboarding_done` only, or make the fallback reachable by checking a sentinel instead of truthiness.
- Log the swallowed exception in `_finish` (line 130) instead of `pass`, and only flip state flags on success (or persist first, then mutate).
- Add an idempotency guard (e.g., a `finishing` state flag) so `_finish` runs once.
- Use functional state updates for page navigation (`set_page_idx(lambda p: min(p+1, ...))`) to avoid stale increments.
- Add an `AnimatedSwitcher`/fade transition around `_build_slide(_SLIDES[page_idx])` (line 228) for polish; currently the slide swaps abruptly.
- Pass `page` explicitly to `shared_haptics(page)` in `_buzz` for consistency with other screens (e.g., results_screen line 383).
- Optionally disable the CTA button while finishing to prevent double-submit.

## 6) Verdict

File is API-correct against flet 1.0.4 (no missing/hallucinated names). Completion flag round-trips through the controller path. Main defects are a dead StorageService fallback caused by a truthiness check against a non-None default, masked persistence failures, and lack of re-entrancy/idempotency. No crash-level bugs; recommend small hardening edits.
