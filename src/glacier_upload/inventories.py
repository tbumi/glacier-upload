# A tool to upload and manage archives in AWS Glacier Vaults.
# Copyright (C) 2023 Trapsilo P. Bumi tbumi@thpd.io
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json

import boto3
import click


def init_retrieval(vault_name, format, description):
    glacier = boto3.client("glacier")

    job_params = {"Type": "inventory-retrieval", "Format": format}
    if description is not None:
        job_params["Description"] = description

    click.echo("Sending inventory-retrieval initiation request...")
    try:
        response = glacier.initiate_job(vaultName=vault_name, jobParameters=job_params)
    except glacier.exceptions.ResourceNotFoundException as e:
        raise click.ClickException(e.response["Error"]["Message"])

    click.echo(f"Job initiation request received. Job ID: {response['jobId']}")


def get(vault_name, job_id):
    glacier = boto3.client("glacier")

    click.echo("Checking inventory retrieval status...")
    try:
        response = glacier.describe_job(vaultName=vault_name, jobId=job_id)
    except glacier.exceptions.ResourceNotFoundException as e:
        raise click.ClickException(e.response["Error"]["Message"])

    if response["Action"] != "InventoryRetrieval":
        raise click.ClickException(
            "Job is not an inventory retrieval. Check the Job ID again."
        )

    click.echo(f"Inventory status: {response['StatusCode']}")

    if not response["Completed"]:
        click.echo("Inventory is not completed.")
        return

    click.echo("Retrieving job data...")
    response = glacier.get_job_output(vaultName=vault_name, jobId=job_id)

    if response["contentType"] == "application/json":
        inventory_json = json.load(response["body"])
        click.echo(json.dumps(inventory_json, indent=2))
    else:
        click.echo(response["body"].read())
