from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_logs as logs,
    aws_rds as rds,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    Duration,
    RemovalPolicy,
    SecretValue,
)

from constructs import Construct
import json


class Ctfd(Construct):
    """Ctfd base construct class."""

    def __init__(
        self, scope, id, cluster, database_name="ctfd", mysql_user="ctfd", **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        mysql_task_definition = ecs.FargateTaskDefinition(
            self, id="ctfd_mysql_task_def"
        )

        mysql_user_pass = secretsmanager.Secret(
            self,
            id="ctfd_mysql_user_pass",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True
            ),
        )

        mysql_task_definition.add_container(
            id="mysql_container",
            image=ecs.ContainerImage.from_registry("mariadb:10.4.12"),
            command=[
                "mysqld",
                "--character-set-server=utf8mb4",
                "--collation-server=utf8mb4_unicode_ci",
                "--wait_timeout=28800",
                "--log-warnings=0",
            ],
            environment={"MYSQL_USER": mysql_user, "MYSQL_DATABASE": database_name},
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="ctfd_mysql_",
                log_group=logs.LogGroup(
                    self,
                    id="ctfd_mysql_log_group",
                    removal_policy=RemovalPolicy.DESTROY,
                    retention=logs.RetentionDays.ONE_WEEK,
                ),
            ),
            secrets={
                "MYSQL_PASSWORD": ecs.Secret.from_secrets_manager(mysql_user_pass),
                "MYSQL_ROOT_PASSWORD": ecs.Secret.from_secrets_manager(
                    secretsmanager.Secret(
                        self,
                        id="ctfd_mysql_root_pass",
                        generate_secret_string=secretsmanager.SecretStringGenerator(
                            exclude_punctuation=True
                        ),
                    )
                ),
            },
            port_mappings=[ecs.PortMapping(container_port=3306)],
        )

        ctfd_mysql_service = ecs_patterns.NetworkLoadBalancedFargateService(
            self,
            id="ctfd_mysql",
            memory_limit_mib=1024,
            cpu=512,
            task_definition=mysql_task_definition,
            cluster=cluster,
            health_check_grace_period=Duration.minutes(5),
            listener_port=3306,
            public_load_balancer=False,
        )

        # ctfd_mysql_creds = rds.Credentials.from_generated_secret(username=mysql_user)

        # ctfd_mysql = rds.DatabaseInstance(
        #    self,
        #    id="ctfd_mysql",
        #    credentials=ctfd_mysql_creds,
        #    engine=rds.MariaDbEngineVersion.VER_10_4_13,
        #    allocated_storage=100, # GB
        #    database_name=database_name,
        #    instance_type=ec2.InstanceType("t3.small"),
        #    vpc=cluster.vpc,
        #    cloudwatch_logs_retention=logs.RetentionDays.ONE_WEEK,
        #    deletion_protection=False,
        #    preferred_maintenance_window="Sun:17:00-Sun:17:30",
        #    publicly_accessible=False
        # )

        ctfd_redis_service = ecs_patterns.NetworkLoadBalancedFargateService(
            self,
            id="ctfd_redis",
            memory_limit_mib=1024,
            cpu=512,
            task_image_options=ecs_patterns.NetworkLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("redis:4"),
                container_port=6379,
                log_driver=ecs.LogDriver.aws_logs(
                    stream_prefix="ctfd_redis_",
                    log_group=logs.LogGroup(
                        self,
                        id="ctfd_redis_log_group",
                        removal_policy=RemovalPolicy.DESTROY,
                        retention=logs.RetentionDays.ONE_WEEK,
                    ),
                ),
            ),
            cluster=cluster,
            health_check_grace_period=Duration.minutes(5),
            listener_port=6379,
            public_load_balancer=False,
        )

        ctfd_s3 = s3.Bucket(
            self,
            id="ctfd_s3_uploads",
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        ctfd_mysql_secret_url = secretsmanager.Secret(
            self,
            id="ctfd_mysql_db_url",
            secret_string_beta1=secretsmanager.SecretStringValueBeta1.from_token(
                json.dumps(
                    {
                        "url": f"mysql+pymysql://{mysql_user}:{mysql_user_pass.secret_value.to_string()}@{ctfd_mysql_service.load_balancer.load_balancer_dns_name}/{database_name}"
                    }
                )
            ),
        )

        ctfd_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            id="ctfd_ctfd",
            assign_public_ip=True,
            memory_limit_mib=1024,
            cpu=512,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            cluster=cluster,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("ctfd/ctfd"),
                container_port=8000,
                environment={
                    "UPLOAD_PROVIDER": "s3",
                    "AWS_S3_BUCKET": ctfd_s3.bucket_name,
                    "AWS_S3_ENDPOINT_URL": ctfd_s3.bucket_regional_domain_name,
                    "REDIS_URL": f"redis://{ctfd_redis_service.load_balancer.load_balancer_dns_name}:6379",
                    "WORKERS": "1",
                    "ACCESS_LOG": "-",
                    "ERROR_LOG": "-",
                    "REVERSE_PROXY": "true",
                },
                log_driver=ecs.LogDriver.aws_logs(
                    stream_prefix="ctfd_ctfd_",
                    log_group=logs.LogGroup(
                        self,
                        id="ctfd_ctfd_log_group",
                        removal_policy=RemovalPolicy.DESTROY,
                        retention=logs.RetentionDays.ONE_WEEK,
                    ),
                ),
                secrets={
                    "DATABASE_URL": ecs.Secret.from_secrets_manager(
                        ctfd_mysql_secret_url, field="url"
                    )
                },
            ),
        )

        ctfd_s3.grant_read_write(ctfd_service.task_definition.task_role)
