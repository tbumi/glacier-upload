# A tool to upload and manage archives in AWS Glacier Vaults.
# Copyright (C) 2016 Trapsilo P. Bumi tbumi@thpd.io
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
import hashlib
import math
import os.path
import sys
import tarfile
import tempfile
import threading

import boto3
import click

MAX_UPLOAD_ATTEMPTS = 10  # 10 retries for each part before failing


def upload(vault_name, file_name, arc_desc, part_size, num_threads, upload_id):
    glacier = boto3.client("glacier")

    if not math.log2(part_size).is_integer():
        raise ValueError("part-size must be a power of 2")
    if part_size < 1 or part_size > 4096:
        raise ValueError("part-size must be between 1 MB and 4096 MB")

    if len(file_name) > 1 or os.path.isdir(file_name[0]):
        click.echo("Consolidating files...")
        file_to_upload = tempfile.TemporaryFile()
        tar = tarfile.open(fileobj=file_to_upload, mode="w:xz")
        for filename in file_name:
            tar.add(filename)
        tar.close()
        click.echo("Files consolidated.")
    else:
        file_to_upload = open(file_name[0], mode="rb")
        click.echo("Opened single file.")

    part_size = part_size * 1024 * 1024

    file_size = file_to_upload.seek(0, 2)

    if file_size < 4096:
        click.echo("File size is less than 4 KB. Uploading in one request...")

        response = glacier.upload_archive(
            vaultName=vault_name, archiveDescription=arc_desc, body=file_to_upload
        )

        click.echo("Uploaded.")
        click.echo(f"Glacier tree hash: {response['checksum']}")
        click.echo(f"Location: {response['location']}")
        click.echo(f"Archive ID: {response['archiveId']}")
        click.echo("Done.")
        file_to_upload.close()
        return

    # file_size > 4 KB, uploading in parts

    job_list = []
    list_of_checksums = []

    if upload_id is None:
        click.echo("Initiating multipart upload...")
        response = glacier.initiate_multipart_upload(
            vaultName=vault_name, archiveDescription=arc_desc, partSize=str(part_size)
        )
        upload_id = response["uploadId"]

        for byte_pos in range(0, file_size, part_size):
            job_list.append(byte_pos)
            list_of_checksums.append(None)

        num_parts = len(job_list)
        click.echo(
            f"File size is {file_size:,} bytes. Will upload in {num_parts} parts."
        )
    else:
        click.echo(f"Resuming upload with id {upload_id}...")

        click.echo("Fetching already uploaded parts...")
        paginator = glacier.get_paginator("list_parts")
        response = paginator.paginate(vaultName=vault_name, uploadId=upload_id)
        parts = response["Parts"]
        part_size = response["PartSizeInBytes"]

        for byte_pos in range(0, file_size, part_size):
            job_list.append(byte_pos)
            list_of_checksums.append(None)

        num_parts = len(job_list)
        with click.progressbar(parts, label="Verifying uploaded parts") as bar:
            for part_data in bar:
                byte_start = int(part_data["RangeInBytes"].partition("-")[0])
                file_to_upload.seek(byte_start)
                part = file_to_upload.read(part_size)
                checksum = _calculate_tree_hash(part, part_size)

                if checksum == part_data["SHA256TreeHash"]:
                    job_list.remove(byte_start)
                    part_num = byte_start // part_size
                    list_of_checksums[part_num] = checksum

    click.echo("Spawning threads...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        fileblock = threading.Lock()
        futures_list = {}
        for byte_pos in job_list:
            future = executor.submit(
                upload_part,
                byte_pos,
                vault_name,
                upload_id,
                part_size,
                file_to_upload,
                file_size,
                num_parts,
                glacier,
                fileblock,
            )
            futures_list[future] = byte_pos // part_size
        done, not_done = concurrent.futures.wait(
            futures_list, return_when=concurrent.futures.FIRST_EXCEPTION
        )
        if len(not_done) > 0:
            # an exception occured
            for future in not_done:
                future.cancel()
            for future in done:
                e = future.exception()
                if e is not None:
                    click.echo(f"Exception occured: {e}")
            click.echo(f"Upload can still be resumed. Upload ID: {upload_id}")
            click.echo("Exiting.")
            file_to_upload.close()
            sys.exit(1)
        else:
            # all threads completed without raising an Exception
            for future in done:
                job_index = futures_list[future]
                list_of_checksums[job_index] = future.result()

    if len(list_of_checksums) != num_parts:
        click.echo("List of checksums incomplete. Recalculating...")
        list_of_checksums = []
        for byte_pos in range(0, file_size, part_size):
            part_num = int(byte_pos / part_size)
            click.echo(f"Checksum {part_num + 1} of {num_parts}...")
            file_to_upload.seek(byte_pos)
            part = file_to_upload.read(part_size)
            list_of_checksums.append(_calculate_tree_hash(part, part_size))

    file_to_upload.close()

    total_tree_hash = _calculate_total_tree_hash(list_of_checksums)

    click.echo("Completing multipart upload...")
    response = glacier.complete_multipart_upload(
        vaultName=vault_name,
        uploadId=upload_id,
        archiveSize=str(file_size),
        checksum=total_tree_hash,
    )
    click.echo("Upload successful.")
    click.echo(f"Calculated total tree hash: {total_tree_hash}")
    click.echo(f"Glacier total tree hash: {response['checksum']}")
    click.echo(f"Location: {response['location']}")
    click.echo(f"Archive ID: {response['archiveId']}")
    click.echo("Done.")


def upload_part(
    start_pos,
    vault_name,
    upload_id,
    part_size,
    fp,
    file_size,
    num_parts,
    glacier,
    fileblock,
):
    fileblock.acquire()
    fp.seek(start_pos)
    part = fp.read(part_size)
    fileblock.release()

    end_pos = start_pos + len(part) - 1
    range_header = f"bytes {start_pos}-{end_pos}/{file_size}"
    part_num = start_pos // part_size
    percentage = part_num / num_parts

    click.echo(f"Uploading part {part_num + 1} of {num_parts}... ({percentage:.2%})")

    for i in range(MAX_UPLOAD_ATTEMPTS):
        try:
            response = glacier.upload_multipart_part(
                vaultName=vault_name, uploadId=upload_id, range=range_header, body=part
            )
            checksum = _calculate_tree_hash(part, part_size)
            if checksum != response["checksum"]:
                click.echo("Checksums do not match. Will try again.")
                continue

            # upload success, exit loop
            break
        except Exception:
            click.echo("Upload error:", sys.exc_info()[0])
            click.echo(f"Trying again. Part {part_num + 1}")
    else:
        click.echo(
            "After {MAX_UPLOAD_ATTEMPTS} attempts, "
            "still failed to upload part. Aborting."
        )
        sys.exit(1)

    del part  # freeing memory
    return checksum


def _calculate_tree_hash(part, part_size):
    checksums = []
    upper_bound = min(len(part), part_size)
    step = 1024 * 1024  # 1 MB
    for chunk_pos in range(0, upper_bound, step):
        chunk = part[chunk_pos : chunk_pos + step]
        checksums.append(hashlib.sha256(chunk).hexdigest())
        del chunk
    return _calculate_total_tree_hash(checksums)


def _calculate_total_tree_hash(list_of_checksums):
    tree = list_of_checksums[:]
    while len(tree) > 1:
        parent = []
        for i in range(0, len(tree), 2):
            if i < len(tree) - 1:
                part1 = bytes.fromhex(tree[i])
                part2 = bytes.fromhex(tree[i + 1])
                parent.append(hashlib.sha256(part1 + part2).hexdigest())
            else:
                parent.append(tree[i])
        tree = parent
    return tree[0]
