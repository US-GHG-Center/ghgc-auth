#!/usr/bin/env python3
import subprocess

import aws_cdk as cdk

from infra.stack import AuthStack, BucketPermissions
from config import auth_app_settings

git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
try:
    git_tag = subprocess.check_output(["git", "describe", "--tags"]).decode().strip()
except subprocess.CalledProcessError:
    git_tag = "no-tag"

tags = {
    "Project": "ghgc",
    "Owner": auth_app_settings.owner,
    "Client": "nasa-impact",
    "Stack": auth_app_settings.stage,
    "GitCommit": git_sha,
    "GitTag": git_tag,
}

app = cdk.App()
stack = AuthStack(
    app,
    f"{auth_app_settings.app_name}-stack-{auth_app_settings.stage}",
    auth_app_settings,
)

# Create a data managers group in user pool if data managers role is provided
if data_managers_role_arn := auth_app_settings.data_managers_role_arn:
    stack.add_cognito_group_with_existing_role(
        "ghgc-data-store-managers",
        "Authenticated users assume read write GHGC data access role",
        role_arn=data_managers_role_arn,
    )

# Create Groups
if auth_app_settings.cognito_groups:
    stack.add_cognito_group(
        "ghgc-staging-writers",
        "Users that have read/write-access to the GHGC store and staging datastore",
        {
            "ghgc-data-store-dev": BucketPermissions.read_write,
            "ghgc-data-store": BucketPermissions.read_write,
            "ghgc-data-store-staging": BucketPermissions.read_write,
        },
    )
    stack.add_cognito_group(
        "ghgc-writers",
        "Users that have read/write-access to the GHGC store",
        {
            "ghgc-data-store-dev": BucketPermissions.read_write,
            "ghgc-data-store": BucketPermissions.read_write,
        },
    )

    stack.add_cognito_group(
        "ghgc-staging-readers",
        "Users that have read-access to the GHGC store and staging data store",
        {
            "ghgc-data-store-dev": BucketPermissions.read_only,
            "ghgc-data-store": BucketPermissions.read_only,
            "ghgc-data-store-staging": BucketPermissions.read_only,
        },
    )
    # TODO: Should this be the default IAM role for the user group?
    stack.add_cognito_group(
        "ghgc-readers",
        "Users that have read-access to the GHGC store",
        {
            "ghgc-data-store": BucketPermissions.read_only,
        },
    )

# Generate a resource server (ie something to protect behind auth) with scopes
# (permissions that we can grant to users/services).
stac_registry_scopes = stack.add_resource_server(
    "ghgc-stac-ingestion-registry",
    supported_scopes={
        "stac:register": "Create STAC ingestions",
        "stac:cancel": "Cancel a STAC ingestion",
        "stac:list": "Cancel a STAC ingestion",
    },
)


# Generate a client for a service, specifying the permissions it will be granted.
# In this case, we want this client to be able to only register new STAC ingestions in
# the STAC ingestion registry service.
stack.add_service_client(
    "ghgc-workflows",
    scopes=[
        stac_registry_scopes["stac:register"],
    ],
)

# Generate an OIDC provider, allowing CI workers to assume roles in the account

oidc_thumbprint = auth_app_settings.oidc_thumbprint
oidc_provider_url = auth_app_settings.oidc_provider_url
if oidc_thumbprint and oidc_provider_url:
    stack.add_oidc_provider(
        f"ghgc-oidc-provider-{auth_app_settings.stage}",
        oidc_provider_url,
        oidc_thumbprint,
    )

# Programmatic Clients
stack.add_programmatic_client("ghgc-sdk")

# Frontend Clients
# stack.add_frontend_client('ghgc-dashboard')

for key, value in tags.items():
    cdk.Tags.of(stack).add(key, value)

app.synth()
