import importlib.util
import io
import json
import os
import sys
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
objects: dict[str, str] = {}


class FakeS3:
    def put_object(self, **kwargs):
        objects[kwargs["Key"]] = kwargs["Body"]

    def list_objects_v2(self, **kwargs):
        keys = [k for k in objects if k.startswith(kwargs["Prefix"])]
        return {"Contents": [{"Key": k} for k in keys], "KeyCount": len(keys)}

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(objects[kwargs["Key"]].encode())}


class FakeSqs:
    def send_message(self, **kwargs):
        worker.handler({"Records": [{"body": kwargs["MessageBody"]}]}, None)


clients = {"s3": FakeS3(), "sqs": FakeSqs()}
sys.modules["boto3"] = types.SimpleNamespace(client=lambda name: clients[name])
os.environ.update(QUEUE_URL_ORDER_EVENTS="local", BUCKET_NAME_LOCAL="local")


def load(name):
    path = ROOT / "src" / "lambdas" / name / "index.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


create_order, list_orders, worker = load("create_order"), load("list_orders"), load("order_worker")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode())

    def _route(self, method):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else None
        if self.path == "/api/orders":
            module = create_order if method == "POST" else list_orders
            result = module.handler({"httpMethod": method, "body": body}, None)
            return self._send(result["statusCode"], result["body"])
        page = (ROOT / "src" / "frontend" / "index.html").read_text()
        self._send(200, page, "text/html")

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


print("Open http://localhost:8000")
HTTPServer(("", 8000), Handler).serve_forever()