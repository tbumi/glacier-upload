import boto3
import click


@click.command()
@click.argument('vault_name')
@click.argument('upload_id')
def abort_upload(vault_name, upload_id):
    glacier = boto3.client('glacier')

    click.echo('Aborting upload...')
    glacier.abort_multipart_upload(
        vaultName=vault_name,
        uploadId=upload_id
    )

    click.echo('Aborted.')
