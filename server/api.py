"""Standard-library HTTP API for the local Alchemy runtime."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlparse

from .project_service import ApiError, ProjectService, safe_identifier


class AlchemyApiHandler(BaseHTTPRequestHandler):
    """HTTP handler backed by a ProjectService instance."""

    service: ProjectService

    server_version = "AlchemyDevAgentAPI/0.1"

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle(self, method: str) -> None:
        try:
            payload = self._read_json_body() if method in {"POST", "PATCH"} else {}
            result, status = route_request(self.service, method, self.path, payload)
            self._write_json(result, status=status)
        except ApiError as exc:
            self._write_json(exc.to_dict(), status=exc.status_code)
        except json.JSONDecodeError:
            self._write_json({"error": {"code": "invalid_json", "message": "Request body must be valid JSON."}}, status=400)
        except Exception as exc:  # pragma: no cover - defensive boundary for API process stability.
            self._write_json({"error": {"code": "internal_error", "message": str(exc)}}, status=500)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ApiError(400, "invalid_json", "JSON request body must be an object.")
        return payload

    def _write_json(self, payload: dict[str, object], *, status: int = 200) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def route_request(service: ProjectService, method: str, raw_path: str, payload: dict[str, Any]) -> tuple[dict[str, object], int]:
    parts = [part for part in urlparse(raw_path).path.strip("/").split("/") if part]
    if method == "GET" and parts == ["health"]:
        return {"status": "ok"}, HTTPStatus.OK

    if not parts or parts[0] != "projects":
        raise ApiError(404, "not_found", "Endpoint not found.")

    if method == "POST" and len(parts) == 1:
        return service.create_project(payload), HTTPStatus.CREATED

    if len(parts) < 2:
        raise ApiError(404, "not_found", "Endpoint not found.")

    project_id = safe_identifier(parts[1], "project_id")
    tail = parts[2:]

    if method == "GET" and not tail:
        return service.get_project(project_id), HTTPStatus.OK
    if method == "POST" and tail == ["files"]:
        return service.add_files(project_id, payload), HTTPStatus.OK
    if method == "GET" and tail == ["files"]:
        return service.list_files(project_id), HTTPStatus.OK
    if method == "POST" and tail == ["intake", "build"]:
        return service.build_intake(project_id), HTTPStatus.OK
    if method == "GET" and tail == ["brief"]:
        return service.get_brief(project_id), HTTPStatus.OK
    if method == "GET" and tail == ["context"]:
        return service.get_context(project_id), HTTPStatus.OK
    if method == "POST" and tail == ["plan"]:
        return service.build_plan(project_id), HTTPStatus.OK
    if method == "GET" and tail == ["task-graph"]:
        return service.get_task_graph(project_id), HTTPStatus.OK
    if method == "POST" and tail == ["runs"]:
        return service.run_project(project_id, payload), HTTPStatus.CREATED
    if method == "GET" and len(tail) == 2 and tail[0] == "runs":
        run_id = safe_identifier(tail[1], "run_id")
        return service.get_run(project_id, run_id), HTTPStatus.OK
    if method == "GET" and len(tail) == 3 and tail[0] == "runs" and tail[2] == "events":
        run_id = safe_identifier(tail[1], "run_id")
        return service.get_run_events(project_id, run_id), HTTPStatus.OK
    if method == "GET" and tail == ["delivery"]:
        return service.get_delivery(project_id), HTTPStatus.OK
    if method == "POST" and len(tail) == 2 and tail[0] == "github" and tail[1] == "inspect":
        return service.build_intake(project_id), HTTPStatus.OK

    raise ApiError(404, "not_found", "Endpoint not found.")


def make_handler(service: ProjectService) -> type[AlchemyApiHandler]:
    class BoundAlchemyApiHandler(AlchemyApiHandler):
        pass

    BoundAlchemyApiHandler.service = service
    return BoundAlchemyApiHandler


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    storage_root: str | Path = ".alchemy/server",
) -> ThreadingHTTPServer:
    service = ProjectService(storage_root=storage_root)
    server = ThreadingHTTPServer((host, port), make_handler(service))
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Alchemy document-driven API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--storage-root", default=".alchemy/server")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = serve(host=args.host, port=args.port, storage_root=args.storage_root)
    print(f"Alchemy API listening on http://{args.host}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
