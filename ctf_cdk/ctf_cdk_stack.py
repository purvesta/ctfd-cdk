from aws_cdk import Stack, aws_ec2 as ec2, aws_ecs as ecs
from constructs import Construct

from ctf_cdk.ctfd import Ctfd


class CtfCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ctf_vpc = ec2.Vpc(self, id="ctf_vpc", cidr="10.10.0.0/16", max_azs=2)

        ctf_vpc.add_interface_endpoint(
            id="ecr_docker_endpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
        )

        ctf_vpc.add_interface_endpoint(
            id="secrets_manager_endpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
        )

        ctf_cluster = ecs.Cluster(
            self,
            id="ctf_cluster",
            container_insights=True,
            enable_fargate_capacity_providers=True,
            vpc=ctf_vpc,
        )
        ctfd = Ctfd(self, id="ctfd", cluster=ctf_cluster)
