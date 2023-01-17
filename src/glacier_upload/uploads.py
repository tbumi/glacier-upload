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


def list_all_uploads(vault_name):
    click.echo("Listing all multipart uploads...")

    glacier = boto3.client("glacier")
    paginator = glacier.get_paginator("list_multipart_uploads")
    iterator = paginator.paginate(vaultName=vault_name)
    uploads_list = list(iterator.search("UploadsList"))

    click.echo(json.dumps(uploads_list, indent=2))


def list_parts_in_upload(vault_name, upload_id):
    click.echo("Listing parts in one multipart upload...")

    glacier = boto3.client("glacier")
    paginator = glacier.get_paginator("list_parts")
    iterator = paginator.paginate(vaultName=vault_name, uploadId=upload_id)
    parts_list = list(iterator.search("Parts"))

    click.echo(json.dumps(parts_list, indent=2))
