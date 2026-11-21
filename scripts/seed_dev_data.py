"""Seed a throwaway dev HA config dir with sample Kids Screentime data (not shipped)."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from custom_components.kids_screentime.models import Rules, Segment, Show, Verdict  # noqa: E402

cfg = Path(sys.argv[1])
storage = cfg / ".storage"
storage.mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone.utc).replace(microsecond=0)


def show(key, title, rating, verdict):
    return Show(key, title, rating, 1, rating in ("TV-Y", "TV-Y7"), verdict, "auto", False, now, now)


def seg(i, key, title, app, minutes, hours_ago):
    start = now - timedelta(hours=hours_ago)
    return Segment(f"seed{i}", "media_player.great_room_apple_tv", None, app, title, title, 1, i, "tvshow", key,
                   start, start + timedelta(minutes=minutes), minutes * 60, 300.0, 420.0)


shows = [show("bluey", "Bluey", "TV-Y", Verdict.COUNT), show("moana", "Moana", "PG", Verdict.COUNT),
         show("mystery show", "Mystery Show <b>x</b>", None, Verdict.REVIEW)]
segments = [seg(1, "bluey", "Bluey", "Disney+", 22, 2), seg(2, "moana", "Moana", "Disney+", 55, 26),
            seg(3, "mystery show", "Mystery Show <b>x</b>", "Netflix", 14, 3), seg(4, "bluey", "Bluey", "Disney+", 18, 50)]
rules = Rules(never={"gritty drama"})
data = {
    "version": 1, "minor_version": 1, "key": "kids_screentime",
    "data": {"segments": {s.id: s.to_dict() for s in segments}, "shows": {s.key: s.to_dict() for s in shows},
             "rules": rules.to_dict(), "lookups": {}},
}
(storage / "kids_screentime").write_text(json.dumps(data))
entry = {"entry_id": "devkids0001", "version": 1, "minor_version": 1, "domain": "kids_screentime", "title": "Kids Screentime",
         "data": {"players": [], "week_start": 6}, "options": {}, "pref_disable_new_entities": False,
         "pref_disable_polling": False, "source": "user", "unique_id": "kids_screentime", "disabled_by": None,
         "discovery_keys": {}, "subentries": [], "created_at": now.isoformat(), "modified_at": now.isoformat()}
(storage / "core.config_entries").write_text(json.dumps({"version": 1, "minor_version": 5, "key": "core.config_entries", "data": {"entries": [entry]}}))
(storage / "onboarding").write_text(json.dumps({"version": 4, "minor_version": 1, "key": "onboarding",
    "data": {"done": ["user", "core_config", "analytics", "integration"]}}))
(cfg / "configuration.yaml").write_text("frontend:\nhttp:\n  server_port: 8124\nwebsocket_api:\n")
