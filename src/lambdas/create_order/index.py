import json
import os
import time
import uuid

import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL_ORDER_EVENTS"]


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context):
    raw = event.get("body") or "{}"
    if len(raw) > 1000:
        return _reply(413, {"error": "body too large"})
    try:
        payload = json.loads(raw)
        item = str(payload.get("item", "")).strip()
        quantity = int(payload.get("qty", 0))
    except (ValueError, TypeError):
        return _reply(400, {"error": "invalid JSON"})
    if not item or not 1 <= quantity <= 100:
        return _reply(400, {"error": "item is required and qty must be 1-100"})
    order = {"id": uuid.uuid4().hex[:8], "item": item, "qty": quantity, "created": int(time.time())}
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(order))
    return _reply(202, {"id": order["id"], "status": "queued"})