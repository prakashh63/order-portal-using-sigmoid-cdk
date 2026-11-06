"""Runs `cdk synth` for bin/app.py and checks the template.json against the app's config."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STAGE = re.search(r'^stage = "(\w+)"', (ROOT / "bin" / "app.py").read_text(), re.M).group(1)
PREFIX = f"order-portal-{STAGE}"

pytestmark = pytest.mark.skipif(shutil.which("cdk") is None, reason="cdk CLI is not installed")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("cdk-out")
    subprocess.run(["cdk", "synth", "--quiet", "--output", str(out_dir)], cwd=ROOT, check=True)
    files = list(out_dir.glob("*.template.json"))
    assert len(files) == 1, files
    return json.loads(files[0].read_text())


def of_type(template, resource_type):
    return {k: v for k, v in template["Resources"].items() if v["Type"] == resource_type}


def props(template, resource_type):
    return [v["Properties"] for v in of_type(template, resource_type).values()]


def as_list(value):
    return value if isinstance(value, list) else [value]


def role_actions(template, role_name):
    role_id = next(k for k, v in of_type(template, "AWS::IAM::Role").items()
                   if v["Properties"].get("RoleName") == role_name)
    actions = set()
    for policy in props(template, "AWS::IAM::Policy"):
        if {"Ref": role_id} in policy["Roles"]:
            for statement in policy["PolicyDocument"]["Statement"]:
                actions.update(as_list(statement["Action"]))
    return actions


def test_two_buckets(template):
    names = {p["BucketName"] for p in props(template, "AWS::S3::Bucket")}
    assert names == {f"order-portal-web-{STAGE}-demo", f"order-portal-data-{STAGE}-demo"}


def test_four_lambdas(template):
    functions = {p["FunctionName"]: p for p in props(template, "AWS::Lambda::Function")}
    assert set(functions) == {f"{PREFIX}-{n}" for n in
                              ["create-order", "list-orders", "order-worker", "daily-report"]}
    assert all(f["MemorySize"] == 128 for f in functions.values())
    assert functions[f"{PREFIX}-daily-report"]["Timeout"] == 30
    assert functions[f"{PREFIX}-create-order"]["Timeout"] == 10


def test_api_routes_and_limits(template):
    methods = props(template, "AWS::ApiGateway::Method")
    real = [m for m in methods if m["HttpMethod"] != "OPTIONS"]
    assert sorted(m["HttpMethod"] for m in real) == ["GET", "POST"]
    stage = props(template, "AWS::ApiGateway::Stage")[0]
    assert stage["StageName"] == "v1"
    assert any(m["ThrottlingRateLimit"] == 5 and m["ThrottlingBurstLimit"] == 10
               for m in stage["MethodSettings"])


def test_queue_and_trigger(template):
    names = {p["QueueName"] for p in props(template, "AWS::SQS::Queue")}
    assert names == {f"{PREFIX}-order-events", f"{PREFIX}-order-events-dlq"}
    assert len(of_type(template, "AWS::Lambda::EventSourceMapping")) == 1


def test_daily_schedule(template):
    rule = props(template, "AWS::Events::Rule")[0]
    assert rule["Name"] == f"{PREFIX}-daily-report-schedule"
    assert rule["ScheduleExpression"] == "rate(1 day)"


def test_cloudfront_in_front_of_site_and_api(template):
    config = props(template, "AWS::CloudFront::Distribution")[0]["DistributionConfig"]
    assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    assert [b["PathPattern"] for b in config["CacheBehaviors"]] == ["api/*"]


def test_each_function_gets_only_the_access_it_needs(template):
    create = role_actions(template, f"{PREFIX}-create-order-role")
    assert "sqs:SendMessage" in create
    assert not any(a.startswith("s3:") for a in create)

    for name in ["list-orders", "daily-report"]:
        actions = role_actions(template, f"{PREFIX}-{name}-role")
        assert any(a.startswith("s3:") for a in actions)
        assert not any(a.startswith("sqs:") for a in actions)

    worker = role_actions(template, f"{PREFIX}-order-worker-role")
    assert "sqs:ReceiveMessage" in worker
    assert any(a.startswith("s3:") for a in worker)


def test_lambda_environment_variables(template):
    functions = {p["FunctionName"]: p for p in props(template, "AWS::Lambda::Function")}
    variables = lambda name: functions[f"{PREFIX}-{name}"]["Environment"]["Variables"]  # noqa: E731
    assert "QUEUE_URL_ORDER_EVENTS" in variables("create-order")
    for name in ["list-orders", "order-worker", "daily-report"]:
        assert any(k.startswith("BUCKET_NAME_") for k in variables(name))
    assert "QUEUE_URL_ORDER_EVENTS" not in variables("list-orders")