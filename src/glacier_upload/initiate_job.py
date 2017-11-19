import boto3
import click


@click.command()
@click.option('-v', '--vault-name', required=True,
              help='The name of the vault to upload to')
@click.option('-a', '--archive-id', required=True,
              help='ID of the archive to retrieve')
@click.option('-d', '--description',
              help='Description of this job (optional)')
def init_archive_retrieval(vault_name, archive_id, description):
    glacier = boto3.client('glacier')

    job_params = {
        'Type': 'archive-retrieval',
        'ArchiveId': archive_id
    }
    if description is not None:
        job_params['Description'] = description

    print('Sending archive-retrieval initiation request...')

    response = glacier.initiate_job(
        vaultName=vault_name,
        jobParameters=job_params)

    print('Job initiation request recieved. Job ID: {}'.format(response['jobId']))


@click.command()
@click.option('-v', '--vault-name', required=True,
              help='The name of the vault to upload to')
@click.option('-f', '--format', default='JSON', type=click.Choice(['CSV', 'JSON']),
              help='Format to request from glacier')
@click.option('-d', '--description',
              help='Description of this job (optional)')
def init_inventory_retrieval(vault_name, format, description):
    glacier = boto3.client('glacier')

    job_params = {
        'Type': 'inventory-retrieval',
        'Format': format
    }
    if description is not None:
        job_params['Description'] = description

    print('Sending inventory-retrieval initiation request...')

    response = glacier.initiate_job(
        vaultName=vault_name,
        jobParameters=job_params)

    print('Job initiation request recieved. Job ID: {}'.format(response['jobId']))
