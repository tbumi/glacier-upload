import json

import boto3
import click


@click.command()
@click.option('-v', '--vault-name', required=True,
              help='The name of the vault')
def list_all_uploads(vault_name):
    glacier = boto3.client('glacier')
    click.echo('Listing all multipart uploads...')

    response = glacier.list_multipart_uploads(vaultName=vault_name)
    uploads_list = response['UploadsList']
    while 'Marker' in response:
        response = glacier.list_multipart_uploads(
            vaultName=vault_name, marker=response['Marker'])
        uploads_list.extend(response['UploadsList'])

    click.echo(json.dumps(uploads_list, indent=2))


@click.command()
@click.option('-v', '--vault-name', required=True,
              help='The name of the vault')
@click.option('-u', '--upload-id', required=True,
              help='ID of upload to list parts')
def list_parts_in_upload(vault_name, upload_id):
    glacier = boto3.client('glacier')
    click.echo('Listing parts in one multipart upload...')

    response = glacier.list_parts(vaultName=vault_name, uploadId=upload_id)
    parts_list = response['Parts']
    while 'Marker' in response:
        response = glacier.list_parts(
            vaultName=vault_name, marker=response['Marker'])
        parts_list.extend(response['Parts'])

    click.echo(json.dumps(parts_list, indent=2))
