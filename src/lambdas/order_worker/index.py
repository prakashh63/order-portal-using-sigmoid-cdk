import json
import os

import boto3

s3 = boto3.client("s3")
BUCKET = next(v for k, v in os.environ.items() if k.startswith("BUCKET_NAME_"))


def handler(event, context):
    for record in event["Records"]:
        order = json.loads(record["body"])
        order["status"] = "processed"
        s3.put_object(Bucket=BUCKET, Key=f"orders/{order['id']}.json", Body=json.dumps(order))