"""All settings of the order-portal application. Change infrastructure here only."""

from sigmoid_cdk.configs import (
    ApiGatewayConfig,
    ApiRouteConfig,
    EventRuleConfig,
    LambdaConfig,
    QueueConfig,
    S3Config,
    WebAppConfig,
)

APP_NAME = "order-portal"
OWNER_TEAM = "orders-team"
COST_CENTER = "cc-100"

# S3 bucket names are global. If "bucket already exists" appears, change this suffix
# (and the same suffix in the three `aws s3` commands in the workflows).
BUCKET_SUFFIX = "demo"

# Runtime used by the Lambdas below. Any name printed by supported_runtime_names() works,
# for example PYTHON_3_14, NODEJS_22_X, JAVA_21, DOTNET_8, RUBY_3_4.
# A Lambda can also set its own runtime instead of using this one.
LAMBDA_RUNTIME = "PYTHON_3_14"


def build_config(stage: str) -> WebAppConfig:
    """Return the full application config for one stage (dev, staging or prod)."""
    web_bucket = f"{APP_NAME}-web-{stage}-{BUCKET_SUFFIX}"
    data_bucket = f"{APP_NAME}-data-{stage}-{BUCKET_SUFFIX}"

    return WebAppConfig(
        app_name=APP_NAME,
        environment=stage,  # type: ignore[arg-type]
        owner_team=OWNER_TEAM,
        cost_center=COST_CENTER,
        frontend_bucket=S3Config(bucket_name=web_bucket),
        extra_buckets=[S3Config(bucket_name=data_bucket)],
        lambdas=[
            LambdaConfig(
                function_name="create-order",
                entry_point_dir="src/lambdas/create_order",
                runtime=LAMBDA_RUNTIME,
                memory_mb=128,
                timeout_seconds=10,
                send_to_queues=["order-events"],
            ),
            LambdaConfig(
                function_name="list-orders",
                entry_point_dir="src/lambdas/list_orders",
                runtime=LAMBDA_RUNTIME,
                memory_mb=128,
                timeout_seconds=10,
                read_write_buckets=[data_bucket],
            ),
            LambdaConfig(
                function_name="order-worker",
                entry_point_dir="src/lambdas/order_worker",
                runtime=LAMBDA_RUNTIME,
                memory_mb=128,
                timeout_seconds=10,
                read_write_buckets=[data_bucket],
            ),
            LambdaConfig(
                function_name="daily-report",
                entry_point_dir="src/lambdas/daily_report",
                runtime=LAMBDA_RUNTIME,
                memory_mb=128,
                timeout_seconds=30,
                read_write_buckets=[data_bucket],
            ),
        ],
        api_gateways=[
            ApiGatewayConfig(
                api_name="orders-api",
                stage_name="v1",
                rate_limit=5,
                burst_limit=10,
                routes=[
                    ApiRouteConfig(
                        path="api/orders",
                        http_method="POST",
                        lambda_name="create-order",
                    ),
                    ApiRouteConfig(
                        path="api/orders",
                        http_method="GET",
                        lambda_name="list-orders",
                    ),
                ],
            ),
        ],
        queues=[
            QueueConfig(queue_name="order-events", consumer_lambda="order-worker"),
        ],
        event_rules=[
            EventRuleConfig(
                rule_name="daily-report-schedule",
                schedule_expression="rate(1 day)",
                target_lambda="daily-report",
            ),
        ],
    )