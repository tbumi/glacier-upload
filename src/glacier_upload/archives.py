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

import os

import boto3
import click


def init_retrieval(vault_name, archive_id, description):
    glacier = boto3.client("glacier")

    job_params = {"Type": "archive-retrieval", "ArchiveId": archive_id}
    if description is not None:
        job_params["Description"] = description

    click.echo("Sending archive-retrieval initiation request...")
    try:
        response = glacier.initiate_job(vaultName=vault_name, jobParameters=job_params)
    except glacier.exceptions.ResourceNotFoundException as e:
        raise click.ClickException(e.response["Error"]["Message"])

    click.echo(f"Job initiation request received. Job ID: {response['jobId']}")


def get(vault_name, job_id, file_name):
    glacier = boto3.client("glacier")

    click.echo(f"Checking status of job {job_id} in {vault_name}...")
    try:
        response = glacier.describe_job(vaultName=vault_name, jobId=job_id)
    except glacier.exceptions.ResourceNotFoundException as e:
        raise click.ClickException(e.response["Error"]["Message"])

    if response["Action"] != "ArchiveRetrieval":
        raise click.ClickException(
            "Job is not an archive retrieval. Check the Job ID again."
        )

    click.echo(f"Job status: {response['StatusCode']}")

    if not response["Completed"]:
        click.echo("Job is not completed.")
        return

    if os.path.lexists(file_name):
        click.confirm(
            f"Are you sure you want to overwrite the file {file_name}?", abort=True
        )

    click.echo("Retrieving job data...")
    response = glacier.get_job_output(vaultName=vault_name, jobId=job_id)

    content_length = int(response["ResponseMetadata"]["HTTPHeaders"]["content-length"])
    response_stream = response["body"]
    try:
        download_archive(content_length, response_stream, file_name)
    finally:
        response_stream.close()


def download_archive(content_length, response_stream, file_name):
    click.echo(f"Downloading archive to file {file_name}")
    with open(file_name, "wb") as file:
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
