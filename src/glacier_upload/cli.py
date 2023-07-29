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

import click

from . import archives, inventories, upload


@click.group()
def glacier_cli():
    pass


@glacier_cli.command(name="upload")
@click.option(
    "-d",
    "--arc-desc",
    default="",
    help="The archive description to help identify archives later",
)
@click.option(
    "-p",
    "--part-size",
    "part_size_mb",
    type=int,
    default=8,
    help=(
        "The part size for multipart upload, in megabytes as a power of 2"
        "(e.g. 1, 2, 4, 8). Default: 8"
    ),
)
@click.option(
    "-t",
    "--num-threads",
    type=int,
    default=((os.cpu_count() or 1) * 5),
    help=(
        "The amount of worker threads concurrently uploading data. "
        "Default: Number of CPUs multiplied by 5"
    ),
)
@click.option("-u", "--upload-id", help="If provided, will resume upload with this ID.")
@click.argument("vault_name")
@click.argument("file_name", nargs=-1, type=click.Path(exists=True))
def upload_archive(**args):
    """
    Uploads FILE_NAME to an AWS Glacier Vault named VAULT_NAME. If FILE_NAME is more
    than 1, they will be consolidated into a tar file before uploaded. If FILE_NAME
    is a directory, the directory and its contents will be consolidated into a single
    tar file and uploaded.
    """
    return upload.upload_archive(**args)


@glacier_cli.group(name="inventory")
def inventory_group():
    """
    Initiate or get an inventory retrieval job.
    """
    pass


@inventory_group.command(name="init-retrieval")
@click.option(
    "-f",
    "--format",
    default="JSON",
    type=click.Choice(["CSV", "JSON"]),
    help="Format of the inventory to request from glacier. Default: JSON",
)
@click.option("-d", "--description", help="Description of this job")
@click.argument("vault_name")
def init_inventory_retrieval(vault_name, format, description):
    """
    Initiate inventory retrieval for all archives in VAULT_NAME.

    This function tells AWS to start creating a list of all archives that exist
    in the vault. Because of the way archives are stored in glacier, this list
    cannot be available immediately. The inventory will be completed between
    several minutes to several hours. To check and retrieve the status of
    this job, run get-inventory with the vault name and job ID
    returned by this function.
    """
    return inventories.init_retrieval(vault_name, format, description)


@inventory_group.command(name="get")
@click.argument("vault_name")
@click.argument("job_id")
def get_inventory(vault_name, job_id):
    """
    Get the output of an inventory retrieval job identified by JOB_ID in VAULT_NAME.

    The inventory job must have already been initialized by init-inventory-retrieval.
    """
    return inventories.get(vault_name, job_id)


@glacier_cli.group(name="archive")
def archive_group():
    """
    Initiate or get an archive retrieval job.
    """
    pass


@archive_group.command(name="init-retrieval")
@click.option("-d", "--description", help="Description of this job")
@click.option(
    "-t",
    "--tier",
    help="Retrieval tier (Expedited, Standard, or Bulk)",
    default="Standard",
    show_default=True,
)
@click.argument("vault_name")
@click.argument("archive_id")
def init_archive_retrieval(vault_name, archive_id, description, tier):
    """
    Initiate retrieval for the archive designated by ARCHIVE_ID in VAULT_NAME.

    To retrieve an archive from glacier, use this function. Because of the
    way archives are stored in glacier, it will take some time to retrieve
    the archive. To check the status and retrieve the archive, run
    glacier-get-archive with the vault name and job ID returned by this function.
    """
    return archives.init_retrieval(vault_name, archive_id, description, tier)


@archive_group.command(name="get")
@click.argument("vault_name")
@click.argument("job_id")
@click.argument(
    "file_name",
    type=click.Path(dir_okay=False, writable=True),
)
def get_archive(vault_name, job_id, file_name):
    """
    Get the output of an archive retrieval job identified by JOB_ID in VAULT_NAME
    and save it to FILE_NAME.

    The archive retrieval job must have already been initialized by
    glacier-init-archive-retrieval command.
    """
    return archives.get(vault_name, job_id, file_name)
