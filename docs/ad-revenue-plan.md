# Ad Revenue Plan — what would earn more, and what it costs

Context: ads are the app's primary income. This document lists only
**revenue-positive** work, each rated for impact and risk. Nothing here has
been implemented — the 2.3.0 build awaiting your phone test is unchanged.

## What the ad setup is today (verified in code)

- **Banners**: `build_banner_ad()` on Home (×2), Networks (sites), History.
  Constructed fresh on each of those screens' re-renders, which happen on
  discrete user actions (search, mode switch, filter) — **not** per progress
  tick. I checked this specifically: `HomeScreen` only ever *writes*
  `progress_version` and never reads it, so the scan's 2 Hz flusher does not
  touch the Home banner. `ResultsScreen` is the screen that does re-render
  at 2 Hz — and it has **no banner at all**.
- **Interstitials**: one per username search, one per email search. Preloaded
  at startup. No minimum interval between shows, no export trigger.

## The opportunities, ranked by value-per-risk

### 1. Put a banner on the Results screen  ← biggest win, lowest risk

The Results screen is where users spend the most wall-clock time: watching a
multi-minute scan tick, then reading and tapping through results. It is also
the one screen that re-renders constantly, so an ad placed there is *visible*
the whole scan runs. Today that entire session earns zero banner revenue.

- **Impact**: high — new viewable inventory on the highest-attention screen.
- **Risk**: very low — purely additive, same `build_banner_ad()` helper the
  other three screens already use, same mobile-only guard.
- **Policy**: one banner per screen, below the results list, no overlap with
  the active-scan banner.

### 2. Interstitial on dossier export  ← high value, natural moment

Exporting a PDF/XMind/CSV is a "I got what I came for" moment. Users expect a
pause there, and it is the standard placement for this app category. Currently
export is completely free.

- **Impact**: high — an extra impression at the highest-intent moment, from
  users who are engaged rather than annoyed.
- **Risk**: low — but it must share the minimum-interval guard below so a user
  who searches and immediately exports does not see two ads back to back.

### 3. Minimum interval between interstitials  ← protects the account

Right now the only guard is "one per search". A user doing search → export →
search → export can stack them. AdMob treats back-to-back interstitials as a
policy violation risk, and a policy strike on your top-earning app costs far
more than the marginal impression.

- **Impact**: protective rather than additive — keeps the account healthy.
- **Risk**: very low. Suggested: 45 s minimum between interstitials; the
  preloaded ad stays preloaded and simply waits.

### 4. Stabilise the banner on Home/History/Networks

Those screens construct a fresh `BannerAd` on each re-render, so every search
or mode switch discards a live banner and requests a new one. That resets
AdMob's own auto-refresh cycle and causes a visible flash.

- **Impact**: medium — better viewability and a cleaner refresh cycle rather
  than strictly more impressions.
- **Risk**: medium — this one *touches existing ad behaviour*, so it is the
  only item I would want to test in isolation on a device before shipping.

## What I deliberately did not propose

- **Interstitial on app resume or tab switches** — highest raw impression
  count, also the fastest way to earn a policy strike and one-star reviews.
  Not worth it on your primary earner.
- **Banner on Settings** — lowest-attention screen; a user changing settings
  who is interrupted by an ad is a churn risk.
- **Two banners on one screen** — against AdMob policy.

## Recommended sequencing

1. Items 1 + 2 + 3 together — they are additive, independent of each other,
   and testable in one phone session after 2.3.0 is validated.
2. Item 4 separately, after watching the current flash behaviour on-device.

Nothing in this list requires a new dependency; all of it uses the existing
`flet-ads` API and the existing `build_banner_ad()` helper.
