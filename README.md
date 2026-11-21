# HA-Kids-Screentime-Tracking

A Home Assistant integration that tracks how much screen time a child gets on your Apple TVs.
It records play sessions on the Apple TV `media_player` entities you choose, keeps only kids'
content, and shows minutes per day and per week, per app and per show.

- Counts **playing** time only; paused, idle and menus don't count.
- Classifies titles by age rating (via TMDB), kids' apps, and your own lists. Adult titles are
  discarded and leave no readable trace in storage.
- Titles it can't classify go to **Needs review** and are held out of the totals until you decide.
- An admin sidebar panel (**Kids Screentime**) lists every recorded session and every gathered
  show or movie, with delete. Deleting a show removes its sessions and blocks it; the Shows tab
  can undo that.
- Sensors: `sensor.kids_screentime_today`, `sensor.kids_screentime_this_week`,
  `sensor.kids_screentime_pending_review` (minutes, with per-app and per-show attributes).

## Install

1. Copy `custom_components/kids_screentime` into your HA `config/custom_components/` (or add this
   repo to HACS as a custom repository) and restart Home Assistant.
2. Settings → Devices & services → Add integration → **Kids Screentime Tracking**.
3. Pick the Apple TV media players, choose the week start day, and (optionally) paste a TMDB key.

### TMDB API key (free)

Create a TMDB account, then Settings → API → request a key (type: Developer). Paste the
**API Key (v3 auth)** into the integration. Without a key the integration still works, using
only the kids' apps list and your always/never lists; everything else goes to Needs review.
Only the title (and a year when known) is sent to TMDB, once per title; results are cached.

This product uses the TMDB API but is not endorsed or certified by TMDB.

## Rules, in order

1. Your **never-count** list → discarded. 2. Your **always-count** list → counted.
3. YouTube / YouTube Kids → ignored; Disney Junior and PBS Kids → counted.
4. Rating `TV-Y`, `TV-Y7`, `TV-Y7-FV`, `TV-G`, `G`, `PG` → counted; `TV-14`, `TV-MA`, `R`,
   `NC-17` → discarded; anything else (including `TV-PG`) → Needs review.
5. No rating: TMDB genre *Kids* → counted; otherwise Needs review.

Design calls worth knowing: segments shorter than 15 seconds are dropped; if two TVs play kids'
content at once, both count; the open session is saved every 5 minutes so a crash loses at most that.

## Services and API

Services: `kids_screentime.delete_session`, `delete_show`, `set_show_rule`, `resolve_review`.
Admin-only websocket commands (`kids_screentime/summary`, `sessions`, `shows`, `review`, and the
write commands) back the panel and the HaCasa2 dashboard.

## Known limits

- Apple TVs only; no iPad or phone. YouTube is ignored.
- What each streaming app reports varies. An app that sends no title is tracked at app level.
- Home Assistant can't see which tvOS profile is active, so time can't be split by profile.
- Percent watched is an estimate (furthest position over total length).

## Development

```bash
uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
```

`scripts/seed_dev_data.py` seeds a throwaway HA config dir with sample data for trying the panel.
