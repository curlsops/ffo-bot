import json
from io import StringIO
from unittest.mock import patch

from bot.services import spotapi_worker


class TestSpotapiWorkerMain:
    def test_success_track(self):
        stdin = StringIO(json.dumps({"operation": "track", "id": "tid"}))
        with (
            patch("sys.stdin", stdin),
            patch(
                "bot.services.spotapi_sync.run_spotapi_operation_sync",
                return_value="Artist - Song",
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            code = spotapi_worker.main()
        assert code == 0
        assert json.loads(stdout.getvalue()) == {"ok": True, "result": "Artist - Song"}

    def test_invalid_request_json(self):
        stdin = StringIO("not-json")
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            code = spotapi_worker.main()
        assert code == 1
        assert json.loads(stdout.getvalue())["ok"] is False

    def test_invalid_request_fields(self):
        stdin = StringIO(json.dumps({"operation": 1, "id": None}))
        with patch("sys.stdin", stdin):
            assert spotapi_worker.main() == 1

    def test_operation_error(self):
        stdin = StringIO(json.dumps({"operation": "track", "id": "tid"}))
        with (
            patch("sys.stdin", stdin),
            patch(
                "bot.services.spotapi_sync.run_spotapi_operation_sync",
                side_effect=RuntimeError("boom"),
            ),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            code = spotapi_worker.main()
        assert code == 1
        assert json.loads(stdout.getvalue()) == {"ok": False, "error": "RuntimeError"}
