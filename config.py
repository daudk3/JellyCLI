import json
import os

CONFIG_PATH = os.path.expanduser("./config.json")
DEFAULT_CONFIG = {
    "oid_provider": "authelia",
}


def _merge_defaults(config: dict | None) -> dict:
    merged = dict(DEFAULT_CONFIG)
    if isinstance(config, dict):
        merged.update(config)
    return merged


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            loaded = json.load(f)
        merged = _merge_defaults(loaded)
        if merged != loaded:
            save_config(merged)
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(config):
    config_to_save = _merge_defaults(config)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_to_save, f, indent=4)
