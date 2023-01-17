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

from . import archives, inventories, upload_archive, uploads


@click.group()
def glacier_cli():
    pass


@glacier_cli.command("upload")
@click.option(
    "-d",
    "--arc-desc",
    default="",
    help="The archive description to help identify archives later",
)
@click.option(
    "-p",
    "--part-size",
    type=int,
    default=8,
    help=(
        "The part size for multipart upload, in "
        "megabytes (e.g. 1, 2, 4, 8) default: 8"
    ),
)
@click.option(
    "-t",
    "--num-threads",
    type=int,
    default=((os.cpu_count() or 1) * 5),
    help="The amount of concurrent threads (default: Number of CPUs multiplied by 5)",
)
@click.option("-u", "--upload-id", help="If provided, will resume upload with this ID.")
@click.argument("vault_name")
@click.argument("file_name", nargs=-1, type=click.Path(exists=True))
def upload_command(*args):
    """
    Uploads FILE_NAME to an AWS Glacier Vault named VAULT_NAME. If FILE_NAME is more
    than 1, they will be consolidated into a tar file before uploaded. If FILE_NAME
    is a directory, the directory and its contents will be consolidated into a single
    tar file and uploaded.
    """
    return upload_archive.upload(*args)


@glacier_cli.command()
@click.argument("vault_name")
def list_all_uploads_command(vault_name):
    """
    Lists all glacier uploads currently pending in VAULT_NAME.
    """
    return uploads.list_all_uploads(vault_name)


@glacier_cli.command()
@click.argument("vault_name")
@click.argument("upload_id")
def list_parts_in_upload_command(vault_name, upload_id):
    """
    List all parts that have been uploaded so far in VAULT_NAME
    as a part of a multipart upload batch identified by UPLOAD_ID.
    """
    return uploads.list_parts_in_upload(vault_name, upload_id)


@glacier_cli.command()
@click.option(
    "-f",
    "--format",
    default="JSON",
    type=click.Choice(["CSV", "JSON"]),
    help="Format of the inventory to request from glacier",
)
@click.option("-d", "--description", help="Description of this job")
@click.argument("vault_name")
def init_inventory_retrieval_command(vault_name, format, description):
    """
    Initiate inventory retrieval for all archives in VAULT_NAME.

    This function tells AWS to start creating a list of all archives that exist
    in the vault. Because of the way archives are stored in glacier, this list
    cannot be available immediately. The inventory will be completed between
    several minutes to several hours. To check and retrieve the status of
    this job, run get-inventory with the vault name and job ID
    returned by this function.
    """
    return inventories.init_inventory_retrieval(vault_name, format, description)


@glacier_cli.command()
@click.argument("vault_name")
@click.argument("job_id")
def get_inventory_command(vault_name, job_id):
    """
    Get the output of an inventory retrieval job identified by JOB_ID in VAULT_NAME.

    The inventory job must have already been initialized by init-inventory-retrieval.
    """
    return inventories.get_inventory(vault_name, job_id)


@glacier_cli.command()
@click.option("-d", "--description", help="Description of this job")
@click.argument("vault_name")
@click.argument("archive_id")
def init_archive_retrieval_command(vault_name, archive_id, description):
    """
    Initiate retrieval for the archive designated by ARCHIVE_ID in VAULT_NAME.

    To retrieve an archive from glacier, use this function. Because of the
    way archives are stored in glacier, it will take some time to retrieve
    the archive. To check the status and retrieve the archive, run
    glacier-get-archive with the vault name and job ID returned by this function.
    """
    return archives.init_archive_retrieval(vault_name, archive_id, description)


@glacier_cli.command()
@click.option(
    "-f",
    "--file-name",
    default="glacier_archive.tar.xz",
    help="File name of archive to be saved",
    type=click.Path(exists=False),
)
@click.argument("vault_name")
@click.argument("job_id")
def get_archive_command(vault_name, job_id, file_name):
    """
    Get the output of an archive retrieval job identified by JOB_ID in VAULT_NAME.

    The archive retrieval job must have already been initialized by
    glacier-init-archive-retrieval command.
    """
    return archives.get_archive(vault_name, job_id, file_name)
