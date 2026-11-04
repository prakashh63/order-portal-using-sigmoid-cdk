from sigmoid_cdk import SigmoidApp
from sigmoid_cdk.configs import (
    ApiGatewayConfig,
    ApiRouteConfig,
    EventRuleConfig,
    LambdaConfig,
    QueueConfig,
    S3Config,
    WebAppConfig,
)

stage = "dev"  # change to "staging" or "prod" here

app = SigmoidApp(
    WebAppConfig(
        app_name="order-portal",
        environment=stage,
        owner_team="orders-team",
        cost_center="cc-100",
        frontend_bucket=S3Config(bucket_name=f"order-portal-web-{stage}-demo"),
        extra_buckets=[S3Config(bucket_name=f"order-portal-data-{stage}-demo")],
        lambdas=[
            LambdaConfig(
                function_name="create-order",
                entry_point_dir="src/lambdas/create_order",
                memory_mb=128,
                timeout_seconds=10,
                send_to_queues=["order-events"],
            ),
            LambdaConfig(
                function_name="list-orders",
                entry_point_dir="src/lambdas/list_orders",
                memory_mb=128,
                timeout_seconds=10,
                read_write_buckets=[f"order-portal-data-{stage}-demo"],
            ),
            LambdaConfig(
                function_name="order-worker",
                entry_point_dir="src/lambdas/order_worker",
                memory_mb=128,
                timeout_seconds=10,
                read_write_buckets=[f"order-portal-data-{stage}-demo"],
            ),
            LambdaConfig(
                function_name="daily-report",
                entry_point_dir="src/lambdas/daily_report",
                memory_mb=128,
                timeout_seconds=30,
                read_write_buckets=[f"order-portal-data-{stage}-demo"],
            ),
        ],
        api_gateways=[
            ApiGatewayConfig(
                api_name="orders-api",
                stage_name="v1",
                rate_limit=5,
                burst_limit=10,
                routes=[
                    ApiRouteConfig(path="api/orders", http_method="POST", lambda_name="create-order"),
                    ApiRouteConfig(path="api/orders", http_method="GET", lambda_name="list-orders"),
                ],
            ),
        ],
        queues=[QueueConfig(queue_name="order-events", consumer_lambda="order-worker")],
        event_rules=[
            EventRuleConfig(
                rule_name="daily-report-schedule",
                schedule_expression="rate(1 day)",
                target_lambda="daily-report",
            ),
        ],
    )
)
app.synth()