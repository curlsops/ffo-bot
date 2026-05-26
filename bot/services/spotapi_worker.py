import json
import sys

from bot.services.spotapi_sync import run_spotapi_operation_sync


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError:
        json.dump({"ok": False, "error": "invalid_request"}, sys.stdout)
        return 1
    operation = request.get("operation")
    entity_id = request.get("id")
    if not isinstance(operation, str) or not isinstance(entity_id, str):
        json.dump({"ok": False, "error": "invalid_request"}, sys.stdout)
        return 1
    try:
        result = run_spotapi_operation_sync(operation, entity_id)
    except Exception as e:
        json.dump({"ok": False, "error": type(e).__name__}, sys.stdout)
        return 1
    json.dump({"ok": True, "result": result}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
