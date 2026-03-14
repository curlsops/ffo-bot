import json


def repair_servers_config(cfg) -> dict | None:
    if isinstance(cfg, dict):
        return cfg
    if isinstance(cfg, list):
        for item in reversed(cfg):
            if isinstance(item, str):
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:  # try next decode attempt
                    pass
    return None
