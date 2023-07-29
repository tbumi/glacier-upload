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
import math
import os.path
import tarfile
import tempfile
import threading
import traceback

import boto3
import click
from tqdm import tqdm

from .utils.tree_hash import calculate_total_tree_hash, calculate_tree_hash

SINGLE_UPLOAD_THRESHOLD_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_UPLOAD_ATTEMPTS = 10  # 10 retries for each part before failing

# ref: https://docs.aws.amazon.com/amazonglacier/latest/dev/uploading-archive-mpu.html
MAX_NUMBER_OF_PARTS = 10000
MIN_PART_SIZE_MB = 1
MAX_PART_SIZE_MB = 4 * 1024


def upload_archive(
    vault_name, file_name, arc_desc, part_size_mb, num_threads, upload_id
):
    glacier = boto3.client("glacier")

    if part_size_mb < MIN_PART_SIZE_MB or part_size_mb > MAX_PART_SIZE_MB:
        raise click.ClickException(
            f"part-size must be between {MIN_PART_SIZE_MB} and {MAX_PART_SIZE_MB} MB"
        )
    if not math.log2(part_size_mb).is_integer():
        raise click.ClickException("part-size must be a power of 2")

    file_to_upload = None
    try:
        if len(file_name) > 1 or os.path.isdir(file_name[0]):
            click.echo("Consolidating files into a .tar archive...")
            file_to_upload = tempfile.TemporaryFile()
            with tarfile.open(fileobj=file_to_upload, mode="w:xz") as tar:
                for filename in file_name:
                    tar.add(filename)
            click.echo("Files consolidated.")
        else:
            file_to_upload = open(file_name[0], mode="rb")
            click.echo("Opened single file.")

        file_size_bytes = file_to_upload.seek(0, 2)
        file_to_upload.seek(0, 0)  # return file pointer to start of file

        if file_size_bytes < SINGLE_UPLOAD_THRESHOLD_BYTES:
            click.echo(
                f"File size is less than {SINGLE_UPLOAD_THRESHOLD_BYTES:,} bytes. "
                "Uploading in one request..."
            )
            response = glacier.upload_archive(
                vaultName=vault_name, archiveDescription=arc_desc, body=file_to_upload
            )

            click.echo("Uploaded.")
            click.echo(f"Glacier tree hash: {response['checksum']}")
            click.echo(f"Location: {response['location']}")
            click.echo(f"Archive ID: {response['archiveId']}")
        else:
            if (
                math.ceil(file_size_bytes / (part_size_mb * 1024 * 1024))
                > MAX_NUMBER_OF_PARTS
            ):
                target_part_size = file_size_bytes / (10000 * 1024 * 1024)
                new_part_size = MIN_PART_SIZE_MB
                while new_part_size < target_part_size:
                    # find the nearest power of 2 larger than the target part size
                    new_part_size *= 2
                    if new_part_size > MAX_PART_SIZE_MB:
                        raise click.ClickException(
                            "Archive/upload size too large (more than 40 TB)"
                        )
                click.confirm(
                    "Maximum number of parts exceeded, would you like to "
                    f"switch to {new_part_size} MB part size?",
                    default=True,
                    abort=True,
                )
                part_size_mb = new_part_size

            multipart_upload(
                glacier,
                upload_id,
                vault_name,
                arc_desc,
                file_size_bytes,
                part_size_mb * 1024 * 1024,
                file_to_upload,
                num_threads,
            )
    finally:
        if file_to_upload is not None:
            file_to_upload.close()

    click.echo("Done.")


def multipart_upload(
    glacier,
    upload_id,
    vault_name,
    arc_desc,
    file_size_bytes,
    part_size_bytes,
    file_to_upload,
    num_threads,
):
    part_list = {}  # map of byte_start -> checksum
    for byte_start in range(0, file_size_bytes, part_size_bytes):
        part_list[byte_start] = None
    num_parts = len(part_list)

    if upload_id is None:
        click.echo("Initiating multipart upload...")
        response = glacier.initiate_multipart_upload(
            vaultName=vault_name,
            archiveDescription=arc_desc,
            partSize=str(part_size_bytes),
        )
        upload_id = response["uploadId"]

        click.echo(
            f"File size is {file_size_bytes:,} bytes. "
            f"Will upload in {num_parts:,} parts."
        )
    else:
        click.echo(f"Resuming upload with id {upload_id}...")

        click.echo("Fetching already uploaded parts...")
        try:
            paginator = glacier.get_paginator("list_parts")
            response = paginator.paginate(vaultName=vault_name, uploadId=upload_id)
            parts = list(response.search("Parts"))
        except glacier.exceptions.ResourceNotFoundException as e:
            raise click.ClickException(e.response["Error"]["Message"])

        for part_data in tqdm(parts, desc="Verifying uploaded parts"):
            byte_start = int(part_data["RangeInBytes"].partition("-")[0])
            file_to_upload.seek(byte_start)
            part = file_to_upload.read(part_size_bytes)
            checksum = calculate_tree_hash(part, part_size_bytes)

            if checksum == part_data["SHA256TreeHash"]:
                part_list[byte_start] = checksum

    click.echo("Spawning threads...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        fileblock = threading.Lock()
        futures_list = {}
        for byte_pos in [
            part for part, checksum in part_list.items() if checksum is None
        ]:
            future = executor.submit(
                upload_part,
                byte_pos,
                vault_name,
                upload_id,
                part_size_bytes,
                file_to_upload,
                file_size_bytes,
                num_parts,
                glacier,
                fileblock,
            )
            futures_list[future] = byte_pos
        done, not_done = concurrent.futures.wait(
            futures_list, return_when=concurrent.futures.FIRST_EXCEPTION
        )
        if len(not_done) > 0:
            # an exception occurred
            for future in not_done:
                future.cancel()
            for future in done:
                exc = future.exception()
                if exc is not None:
                    exc_string = "".join(traceback.format_exception(exc))
                    click.secho(f"Exception occurred: {exc_string}", err=True, fg="red")
            click.echo(f"Upload can still be resumed. Upload ID: {upload_id}")
            raise click.Abort
        else:
            # all threads completed without raising an Exception
            for future in done:
                byte_start = futures_list[future]
                part_list[byte_start] = future.result()

    total_tree_hash = calculate_total_tree_hash(list(part_list.values()))

    click.echo("Completing multipart upload...")
    response = glacier.complete_multipart_upload(
        vaultName=vault_name,
        uploadId=upload_id,
        archiveSize=str(file_size_bytes),
        checksum=total_tree_hash,
    )
    click.echo("Upload successful.")
    click.echo(f"Calculated total tree hash: {total_tree_hash}")
    click.echo(f"Glacier total tree hash: {response['checksum']}")
    click.echo(f"Location: {response['location']}")
    click.echo(f"Archive ID: {response['archiveId']}")


def upload_part(
    start_pos,
    vault_name,
    upload_id,
    part_size_bytes,
    fp,
    file_size_bytes,
    num_parts,
    glacier,
    fileblock,
):
    with fileblock:
        fp.seek(start_pos)
        part = fp.read(part_size_bytes)

    end_pos = start_pos + len(part) - 1
    range_header = f"bytes {start_pos}-{end_pos}/{file_size_bytes}"
    part_num = start_pos // part_size_bytes
    percentage = part_num / num_parts
    checksum = calculate_tree_hash(part, part_size_bytes)

    click.echo(f"Uploading part {part_num + 1} of {num_parts}... ({percentage:.2%})")

    error = None
    for _ in range(MAX_UPLOAD_ATTEMPTS):
        try:
            response = glacier.upload_multipart_part(
                vaultName=vault_name, uploadId=upload_id, range=range_header, body=part
            )
            if checksum != response["checksum"]:
                raise Exception("Local checksum does not match Glacier checksum")

            # upload success, exit loop
            break
        except Exception as e:
            click.secho(f"Upload error: {e}", err=True, fg="red")
            click.echo(f"Trying again. Part {part_num + 1}")
            error = e
    else:
        click.secho(
            f"After {MAX_UPLOAD_ATTEMPTS} attempts, "
            f"still failed to upload part. Aborting upload of part {part_num + 1}.",
            err=True,
            fg="red",
        )
        if error is not None:
            raise error
        else:
            raise RuntimeError()

    del part  # freeing memory
    return checksum
