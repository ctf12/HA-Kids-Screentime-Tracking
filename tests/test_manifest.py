import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_manifest_declares_integration():
    manifest = json.loads((ROOT / "custom_components/kids_screentime/manifest.json").read_text())
    assert manifest["domain"] == "kids_screentime"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "calculated"
    assert {"http", "websocket_api", "frontend", "panel_custom"} <= set(manifest["dependencies"])


def test_hacs_json_valid():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"]
    assert "render_readme" in hacs
