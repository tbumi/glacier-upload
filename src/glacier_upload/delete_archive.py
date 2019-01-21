import boto3
import click


def delete_archive(vault_name, archive_id):
    glacier = boto3.client('glacier')

    click.echo('Sending delete archive request...')

    glacier.delete_archive(
        vaultName=vault_name,
        archiveId=archive_id)

    click.echo('Delete archive request sent.')

#TODO: the argument name was wrong and wasnt working before
@click.command()
@click.option('-v', '--vault-name', required=True,
              help='The name of the vault')
@click.option('-a', '--archive-id', required=True,
              help='ID of the archive to delete')
def delete_archive_command(vault_name, archive_id):
    return delete_archive(vault_name, archive_id)
