# Apple TV attributes

**Status: not yet verified against the real TVs.** The tracker uses HA's documented `apple_tv`
`media_player` attributes. Confirm them before relying on per-show data.

| Attribute | Used for |
|---|---|
| `state` (`playing`, `paused`, `idle`, `standby`, `off`) | only `playing` counts |
| `media_content_type` (`tvshow`, `movie`, `video`, `music`) | non-video types are ignored |
| `media_title`, `media_series_title`, `media_season`, `media_episode` | show key and episode |
| `media_position`, `media_position_updated_at`, `media_duration` | percent watched |
| `app_id`, `app_name` | app breakdown, kids' apps, YouTube rule |

## How to verify

Play a kids' episode and a movie in each app Helena uses, then in Developer tools → States open
each Apple TV media player and note which of the attributes above are present, and which app
reports no title or no series. If names differ, change the `ATTR_*` constants at the top of
`custom_components/kids_screentime/tracker.py` and add a test with the real values.
