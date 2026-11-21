# Apple TV attributes

**Status: checked against the live house on 20 Nov 2026**, from the Home Assistant recorder
database (real states of the three Apple TV media players). What each app sends differs a lot.

| App | `media_title` | `media_artist` | other | What the tracker gets |
|---|---|---|---|---|
| Disney+ | the **series** ("How I Met Your Mother") | `S1:E21 Milk` (season, episode, episode name) | `media_duration`, `media_content_id`; no content type, no series/season/episode fields | series, season and episode, read from the artist |
| Crave | `Friends ‑ S1 E5 The One With…` (series, season and episode all in one string; the dash is a non-breaking hyphen) | none | `media_content_type: video`, `media_duration` | series, season and episode, read from the title |
| Netflix | **none** | none | only `app_id` and `app_name` | app only; tracked as `app:com.netflix.netflix` |

Netflix does not publish what is playing to tvOS, so neither pyatv nor Home Assistant can read a
title, episode or length from it. This is the app's choice, not a fault in pyatv or the integration.
Time in an app like that can only be tracked at app level, so a viewer cannot be told apart by content.

Also seen: `media_position` was not present in any sampled state, so "percent watched" stays empty
until an app sends it. `state` values seen: `playing`, `paused`, `idle`, `unknown`, `off`, `unavailable`.

The parsing lives in `episode_info()` in `custom_components/kids_screentime/tracker.py`; real
samples are in `tests/fixtures/apple_tv_states.json` and the tests in `tests/test_tracker.py`.
