import importlib.util
import io
import json
import os
import sys
import time
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
objects: dict[str, str] = {}  # fake S3 data bucket: file name -> file content
timeline: list[str] = []  # what every service did, in order


def log(service, message):
    line = f"{time.strftime('%H:%M:%S')}  [{service}] {message}"
    timeline.append(line)
    print(line)


class FakeS3:
    def put_object(self, **kwargs):
        log("S3", f"saved file {kwargs['Key']}")
        objects[kwargs["Key"]] = kwargs["Body"]

    def list_objects_v2(self, **kwargs):
        keys = [k for k in objects if k.startswith(kwargs["Prefix"])]
        return {"Contents": [{"Key": k} for k in keys], "KeyCount": len(keys)}

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(objects[kwargs["Key"]].encode())}


class FakeSqs:
    def send_message(self, **kwargs):
        log("SQS", f"message added to queue order-events: {kwargs['MessageBody']}")
        log("Lambda", "order-worker picked up the message")
        worker.handler({"Records": [{"body": kwargs["MessageBody"]}]}, None)
        log("Lambda", "order-worker finished, message removed from queue")


clients = {"s3": FakeS3(), "sqs": FakeSqs()}
sys.modules["boto3"] = types.SimpleNamespace(client=lambda name: clients[name])
os.environ.update(QUEUE_URL_ORDER_EVENTS="local", BUCKET_NAME_LOCAL="local")


def load(name):
    path = ROOT / "src" / "lambdas" / name / "index.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


create_order, list_orders = load("create_order"), load("list_orders")
worker, daily_report = load("order_worker"), load("daily_report")

DASHBOARD = """<!doctype html><meta charset="utf-8"><title>Local services</title>
<body style="font-family:monospace;max-width:900px;margin:1.5rem auto">
<h3>Local services (fake AWS)</h3>
<button onclick="fetch('/debug/run-daily-report').then(refresh)">
Run daily report (what EventBridge does once a day)</button>
<h4>Timeline</h4><pre id="timeline"></pre>
<h4>S3 data bucket files</h4><pre id="files"></pre>
<script>
async function refresh() {
  const state = await (await fetch('/debug/state')).json();
  document.getElementById('timeline').textContent = state.timeline.join('\\n');
  document.getElementById('files').textContent = Object.keys(state.files).join('\\n') || '(empty)';
}
refresh(); setInterval(refresh, 1000);
</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # the timeline above replaces the default access log

    def _send(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode())

    def _route(self, method):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else None
        if self.path == "/favicon.ico":
            return self._send(404, "")
        if self.path == "/debug":
            return self._send(200, DASHBOARD, "text/html")
        if self.path == "/debug/state":
            return self._send(200, json.dumps({"timeline": timeline, "files": objects}))
        if self.path == "/debug/run-daily-report":
            log("EventBridge", "daily schedule fired")
            result = daily_report.handler({}, None)
            log("Lambda", f"daily-report finished: {result}")
            return self._send(200, json.dumps(result))
        if self.path == "/api/orders":
            module, name = (create_order, "create-order") if method == "POST" else (
                list_orders,
                "list-orders",
            )
            log("CloudFront", f"{method} /api/orders -> forwarded to API Gateway")
            log("API Gateway", f"route matched -> Lambda {name}")
            result = module.handler({"httpMethod": method, "body": body}, None)
            log("Lambda", f"{name} returned status {result['statusCode']}")
            return self._send(result["statusCode"], result["body"])
        log("CloudFront", f"{method} {self.path} -> S3 web bucket: index.html")
        self._send(200, (ROOT / "src" / "frontend" / "index.html").read_text(), "text/html")

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


print("App:       http://localhost:8000")
print("Dashboard: http://localhost:8000/debug  (open this in a second browser tab)")
HTTPServer(("", 8000), Handler).serve_forever()