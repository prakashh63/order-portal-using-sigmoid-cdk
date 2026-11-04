import json
import os

import boto3

s3 = boto3.client("s3")
BUCKET = next(v for k, v in os.environ.items() if k.startswith("BUCKET_NAME_"))


def handler(event, context):
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix="orders/", MaxKeys=50)
    orders = [
        json.loads(s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read())
        for obj in listing.get("Contents", [])
    ]
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"count": len(orders), "orders": orders}),
    }