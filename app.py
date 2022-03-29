#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ctf_cdk.ctf_cdk_stack import CtfCdkStack


app = cdk.App()
CtfCdkStack(app, "CtfCdkStack",
    #env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region="us-east-2"),
)

app.synth()
