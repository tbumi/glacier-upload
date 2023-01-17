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
import os

import boto3
import click


def init_archive_retrieval(vault_name, archive_id, description):
    glacier = boto3.client("glacier")

    job_params = {"Type": "archive-retrieval", "ArchiveId": archive_id}
    if description is not None:
        job_params["Description"] = description

    click.echo("Sending archive-retrieval initiation request...")

    response = glacier.initiate_job(vaultName=vault_name, jobParameters=job_params)

    click.echo(f"Job initiation request recieved. Job ID: {response['jobId']}")


def get_archive(vault_name, job_id, file_name):
    # If file already exists, print warning and return
    if os.path.isfile(file_name):
        click.echo(
            f"File {file_name} already exists. Please delete it or "
            "provide another file name"
        )
        return

    glacier = boto3.client("glacier")

    click.echo(f"Checking status of job {job_id} in {vault_name}...")
    response = glacier.describe_job(vaultName=vault_name, jobId=job_id)

    click.echo(f"Job status: {response['StatusCode']}")

    if not response["Completed"]:
        click.echo("Job is not completed.")
        return

    click.echo("Retrieving job data...")
    response = glacier.get_job_output(vaultName=vault_name, jobId=job_id)

    if response["contentType"] == "application/json":
        inventory_json = json.load(response["body"])
        click.echo(json.dumps(inventory_json, indent=2))
    elif response["contentType"] == "text/csv":
        click.echo(response["body"].read())
    else:
        content_length = int(
            response["ResponseMetadata"]["HTTPHeaders"]["content-length"]
        )
        response_stream = response["body"]
        try:
            download_archive(content_length, response_stream, file_name)
        finally:
            response_stream.close()


def download_archive(content_length, response_stream, file_name):
    click.echo(f"Downloading archive to file {file_name}")
    with open(file_name, "xb") as file:
        if content_length < 4096:
            # Content length is < 4 KB, downloading it in one go
            file.write(response_stream.read())
        else:
            # Download data in chunks of 4 KB
            chunk_size = 4096
            with click.progressbar(
                length=content_length, label="Downloading file"
            ) as bar:
                for chunk in response_stream.iter_chunks(chunk_size):
                    # iter_chunks returns bytes in chunk format
                    # by calling read internally for chunk_size
                    # https://github.com/boto/botocore/blob/51bcacab620bbb35c84157d61b9fed93f2a467f6/botocore/response.py#L125
                    file.write(chunk)
                    bar.update(len(chunk))
