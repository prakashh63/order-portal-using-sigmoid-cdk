"""Prints a readable summary of the synthesized template.json.

Usage: cdk synth && python tools/explain_template.py [cdk.out]
"""

import json
import sys
from pathlib import Path


def of_type(template, resource_type):
    return {k: v for k, v in template["Resources"].items() if v["Type"] == resource_type}


def as_list(value):
    return value if isinstance(value, list) else [value]


def yes(flag):
    return "YES" if flag else "NO"


def tags(resource):
    return {t["Key"]: t["Value"] for t in resource["Properties"].get("Tags", [])}


def role_actions(template, role_id):
    actions = set()
    for policy in of_type(template, "AWS::IAM::Policy").values():
        if {"Ref": role_id} in policy["Properties"]["Roles"]:
            for statement in as_list(policy["Properties"]["PolicyDocument"]["Statement"]):
                actions.update(as_list(statement["Action"]))
    return sorted(actions)


def route_path(resources, logical_id):
    props = resources[logical_id]["Properties"]
    parent = props["ParentId"]
    prefix = f"{route_path(resources, parent['Ref'])}/" if "Ref" in parent else ""
    return prefix + props["PathPart"]


def title(text):
    print(f"\n=== {text} ===")


def explain(template):
    resources = template["Resources"]
    counts = {}
    for resource in resources.values():
        counts[resource["Type"]] = counts.get(resource["Type"], 0) + 1
    title("OVERVIEW (resource type: how many)")
    for name, number in sorted(counts.items()):
        print(f"  {number} x {name}")

    title("S3 BUCKETS")
    for resource in of_type(template, "AWS::S3::Bucket").values():
        p = resource["Properties"]
        blocked = all(p["PublicAccessBlockConfiguration"].values())
        versioned = p.get("VersioningConfiguration", {}).get("Status") == "Enabled"
        print(f"  {p['BucketName']}")
        print(f"     public access blocked: {yes(blocked)}   encrypted: {yes('BucketEncryption' in p)}"
              f"   versioning: {yes(versioned)}   on delete: {resource.get('DeletionPolicy')}")

    title("CLOUDFRONT")
    for p in (r["Properties"] for r in of_type(template, "AWS::CloudFront::Distribution").values()):
        cfg = p["DistributionConfig"]
        print(f"  default (website): {cfg['DefaultCacheBehavior']['ViewerProtocolPolicy']}")
        for behavior in cfg.get("CacheBehaviors", []):
            print(f"  path {behavior['PathPattern']}: {behavior['ViewerProtocolPolicy']} (goes to API Gateway)")
    print(f"  Origin Access Control (S3 private): {yes(of_type(template, 'AWS::CloudFront::OriginAccessControl'))}")

    title("API GATEWAY")
    apis = {k: v["Properties"]["Name"] for k, v in of_type(template, "AWS::ApiGateway::RestApi").items()}
    path_resources = of_type(template, "AWS::ApiGateway::Resource")
    for api_id, api_name in apis.items():
        print(f"  {api_name}")
        for p in (r["Properties"] for r in of_type(template, "AWS::ApiGateway::Method").values()):
            if p["RestApiId"].get("Ref") == api_id and p["HttpMethod"] != "OPTIONS" and "Ref" in p["ResourceId"]:
                print(f"     {p['HttpMethod']:6} /{route_path(path_resources, p['ResourceId']['Ref'])}")
    for stage in (r["Properties"] for r in of_type(template, "AWS::ApiGateway::Stage").values()):
        limits = {(m["ThrottlingRateLimit"], m["ThrottlingBurstLimit"]) for m in stage["MethodSettings"]}
        print(f"  stage {stage['StageName']}: rate/burst limits {sorted(limits)}")

    title("LAMBDA FUNCTIONS")
    for resource in of_type(template, "AWS::Lambda::Function").values():
        p = resource["Properties"]
        role_id = p["Role"]["Fn::GetAtt"][0]
        print(f"  {p['FunctionName']}   {p['Runtime']}, {p['MemorySize']} MB, {p['Timeout']}s timeout")
        print(f"     env vars: {sorted(p['Environment']['Variables'])}")
        print(f"     allowed actions: {role_actions(template, role_id)}")

    title("SQS QUEUES")
    for p in (r["Properties"] for r in of_type(template, "AWS::SQS::Queue").values()):
        extra = f", retries before dead-letter: {p['RedrivePolicy']['maxReceiveCount']}" if "RedrivePolicy" in p else ""
        print(f"  {p['QueueName']}   encrypted: {yes(p.get('SqsManagedSseEnabled'))}{extra}")
    print(f"  queue triggers a Lambda: {len(of_type(template, 'AWS::Lambda::EventSourceMapping'))} time(s)")

    title("EVENTBRIDGE RULES")
    for p in (r["Properties"] for r in of_type(template, "AWS::Events::Rule").values()):
        print(f"  {p['Name']}   runs: {p.get('ScheduleExpression', 'on matching events')}")

    title("LOG GROUPS")
    for p in (r["Properties"] for r in of_type(template, "AWS::Logs::LogGroup").values()):
        print(f"  {p['LogGroupName']}   kept {p['RetentionInDays']} days, KMS encrypted: {yes('KmsKeyId' in p)}")

    title("TAGS (on the first bucket)")
    first_bucket = next(iter(of_type(template, "AWS::S3::Bucket").values()))
    for key, value in sorted(tags(first_bucket).items()):
        print(f"  {key} = {value}")


def main(argv):
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("cdk.out")
    files = sorted(out_dir.glob("*.template.json"))
    if not files:
        print(f"no template found in {out_dir}; run `cdk synth` first")
        return 1
    for path in files:
        print(f"\n##### {path.name}")
        explain(json.loads(path.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))