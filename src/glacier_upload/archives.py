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

import concurrent.futures
import os

import boto3
import click
from tqdm import tqdm, trange

from .utils.tree_hash import calculate_tree_hash

BITE_SIZE = 4096  # 4 KB
CHUNK_SIZE = 32 * 1024 * 1024  # 32 MB


def init_retrieval(vault_name, archive_id, description, tier):
    glacier = boto3.client("glacier")

    job_params = {"Type": "archive-retrieval", "ArchiveId": archive_id, "Tier": tier}
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
        job_desc = glacier.describe_job(vaultName=vault_name, jobId=job_id)
    except glacier.exceptions.ResourceNotFoundException as e:
        raise click.ClickException(e.response["Error"]["Message"])

    if job_desc["Action"] != "ArchiveRetrieval":
        raise click.ClickException(
            "Job is not an archive retrieval. Check the Job ID again."
        )

    click.echo(f"Job status: {job_desc['StatusCode']}")

    if not job_desc["Completed"]:
        click.echo("Job is not completed.")
        return
    if job_desc["StatusCode"] != "Succeeded":
        click.echo("Job unsuccessful, unable to download.")
        return

    if os.path.lexists(file_name):
        click.confirm(
            f"Are you sure you want to overwrite the file {file_name}?", abort=True
        )

    content_length = int(job_desc["ArchiveSizeInBytes"])
    try:
        job_output = glacier.get_job_output(vaultName=vault_name, jobId=job_id)
    except glacier.exceptions.ResourceNotFoundException:
        click.secho("Unable to download, job has expired.", fg="red")
        return

    if content_length < CHUNK_SIZE:
        response_stream = job_output["body"]
        try:
            with open(file_name, "wb") as f:
                with tqdm(
                    total=content_length,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc="Downloading file",
                ) as bar:
                    for chunk in response_stream.iter_chunks(BITE_SIZE):
                        # iter_chunks returns bytes in chunk format
                        # by calling read internally for chunk_size
                        # https://github.com/boto/botocore/blob/51bcacab620bbb35c84157d61b9fed93f2a467f6/botocore/response.py#L125
                        f.write(chunk)
                        bar.update(len(chunk))
        finally:
            response_stream.close()
        return

    parts_dir = f"{file_name}_parts"
    if not os.path.isdir(parts_dir):
        os.mkdir(parts_dir)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_list = {
            executor.submit(
                download_archive_part,
                glacier,
                vault_name,
                job_id,
                file_name,
                start_byte,
            ): start_byte
            for start_byte in range(0, content_length, CHUNK_SIZE)
        }
        with tqdm(
            total=len(future_list),
            unit="part",
            desc="Downloading archive parts",
        ) as bar:
            for future in concurrent.futures.as_completed(future_list):
                bar.update(1)
                result = future.result()  # re-throw any exceptions
                start_byte = future_list[future]
                part_number = start_byte // CHUNK_SIZE
                if result == "skipped":
                    tqdm.write(f"Skipping part {part_number}")
                else:
                    tqdm.write(f"File part {part_number} downloaded")

    with open(file_name, "wb") as final_file:
        for part_number in trange(
            len(future_list),
            unit="part",
            desc="Consolidating archive parts",
        ):
            with open(os.path.join(parts_dir, f"{part_number:04}"), "rb") as part_file:
                final_file.write(part_file.read())

    for part_number in trange(
        len(future_list),
        unit="part",
        desc="Deleting archive parts",
    ):
        os.remove(os.path.join(parts_dir, f"{part_number:04}"))
    os.rmdir(parts_dir)

    click.echo("Archive downloaded.")


def download_archive_part(glacier_client, vault_name, job_id, file_name, start_byte):
    part_number = start_byte // CHUNK_SIZE
    part_file_name = os.path.join(f"{file_name}_parts", f"{part_number:04}")

    download_range = f"bytes={start_byte}-{start_byte+CHUNK_SIZE-1}"
    job_output = glacier_client.get_job_output(
        vaultName=vault_name, jobId=job_id, range=download_range
    )
    if os.path.lexists(part_file_name):
        if verify_file_checksum(part_file_name, job_output["checksum"]):
            return "skipped"
        tqdm.write(f"Checksums do not match for part {part_number}, redownloading")

    response_stream = job_output["body"]
    try:
        with open(part_file_name, "wb") as f:
            with tqdm(
                total=CHUNK_SIZE,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"Download part {part_number}",
                leave=False,
            ) as bar:
                for chunk in response_stream.iter_chunks(BITE_SIZE):
                    f.write(chunk)
                    bar.update(len(chunk))
    finally:
        response_stream.close()

    if not verify_file_checksum(part_file_name, job_output["checksum"]):
        raise Exception(f"Checksums do not match for part {part_number}")


def verify_file_checksum(file_name, checksum, max_size=CHUNK_SIZE):
    # click.echo(f"Glacier checksum: {checksum}")
    with open(file_name, "rb") as f:
        file_contents = f.read()
    calculated_checksum = calculate_tree_hash(file_contents, max_size)
    # click.echo(f"Calculated checksum: {calculated_checksum}")
    return calculated_checksum == checksum
