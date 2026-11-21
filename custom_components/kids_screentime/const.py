"""Constants for Kids Screentime Tracking."""
from datetime import timedelta

DOMAIN = "kids_screentime"

CONF_PLAYERS = "players"
CONF_TMDB_KEY = "tmdb_api_key"
CONF_WEEK_START = "week_start"  # Python weekday, 6 = Sunday

DEFAULT_WEEK_START = 6
MIN_SEGMENT_SECONDS = 15
# A break this short (a pause, an autoplay, the Apple TV briefly reporting another app) is the same viewing.
STITCH_GAP_SECONDS = 30
FLUSH_INTERVAL = timedelta(minutes=5)

COUNT_RATINGS = frozenset({"TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "G", "PG"})
DISCARD_RATINGS = frozenset({"TV-14", "TV-MA", "R", "NC-17"})
DEFAULT_KIDS_APPS = ("disney junior", "pbs kids")

SIGNAL_UPDATED = "kids_screentime_updated"
