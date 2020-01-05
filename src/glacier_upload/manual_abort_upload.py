import boto3
import click


def abort_upload(vault_name, upload_id):
    glacier = boto3.client("glacier")

    click.echo("Aborting upload...")
    glacier.abort_multipart_upload(vaultName=vault_name, uploadId=upload_id)

    click.echo("Aborted.")


@click.command()
@click.option(
    "-v",
    "--vault-name",
    required=True,
    help="The name of the vault for abort upload",
)
@click.option(
    "-u",
    "--upload-id",
    required=True,
    help="upload id for abort upload",
)
def abort_upload_command(vault_name, upload_id):
    return abort_upload(vault_name, upload_id)
