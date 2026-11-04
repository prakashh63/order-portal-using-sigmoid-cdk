import json
import os
import time

import boto3

s3 = boto3.client("s3")
BUCKET = next(v for k, v in os.environ.items() if k.startswith("BUCKET_NAME_"))


def handler(event, context):
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix="orders/")
    report = {"date": time.strftime("%Y-%m-%d"), "total_orders": listing.get("KeyCount", 0)}
    s3.put_object(Bucket=BUCKET, Key=f"reports/{report['date']}.json", Body=json.dumps(report))
    return report