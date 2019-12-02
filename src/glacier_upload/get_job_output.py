import json
import time

import boto3
import click


def get_job_output(vault_name, job_id, file_name, batch_size):
    glacier = boto3.client("glacier")

    click.echo("Checking job status...")
    response = glacier.describe_job(vaultName=vault_name, jobId=job_id)

    click.echo("Job status: {}".format(response["StatusCode"]))

    if not response["Completed"]:
        click.echo("Exiting.")
        return
    else:
        click.echo("Retrieving job data...")
        if response["Action"] == 'ArchiveRetrieval':
            final_byte = int(response["RetrievalByteRange"].split("-")[1])
            print('RetrievalByteRange: ' + response["RetrievalByteRange"])
            batch_size = int(batch_size)
            if final_byte > (batch_size * 2):
                with open(file_name, "xb") as file:
                    for i in range(batch_size, final_byte, batch_size):
                        response = batch_request_retrying(glacier, vault_name, job_id,
                                                          'bytes=' + str(i - batch_size) + '-' + str(i - 1))
                        file.write(response["body"].read())
                        file.flush()
                    print('bytes=' + str(i) + '-' + str(final_byte) + ': last batch')
                    response = batch_request_retrying(glacier, vault_name, job_id,
                                                      'bytes=' + str(i) + '-' + str(final_byte))
                    file.write(response["body"].read())
                    file.flush()
        else:
            response = glacier.get_job_output(vaultName=vault_name, jobId=job_id)

            if response["contentType"] == "application/json":
                inventory_json = json.loads(response["body"].read().decode("utf-8"))
                click.echo(json.dumps(inventory_json, indent=2))
            elif response["contentType"] == "text/csv":
                click.echo(response["body"].read())
            else:
                with open(file_name, "xb") as file:
                    file.write(response["body"].read())


def batch_request_retrying(glacier, vault_name, job_id, byte_range):
    tries = 10
    status_code = 0
    while tries > 0 and status_code != 206:
        response = glacier.get_job_output(vaultName=vault_name, jobId=job_id,
                                          range=byte_range)
        tries -= 1
        status_code = response['status']
        print('getting ' + byte_range)
        time.sleep(5)
    if response['status'] != 206:
        raise

    return response


@click.command()
@click.option(
    "-v",
    "--vault-name",
    required=True,
    help="The name of the vault to upload to",
)
@click.option(
    "-j",
    "--job-id",
    required=True,
    help="Job ID"
)
@click.option(
    "-f",
    "--file-name",
    default="glacier_archive.tar.xz",
    help="File name of archive to be saved, "
         "if the job is an archive-retrieval",
)
@click.option(
    "-b",
    "--batch-size",
    default="67108800",
    help="Size of the byte batch, for download big archive "
         "default is 64 mb",
)
def get_job_output_command(vault_name, job_id, file_name, batch_size):
    return get_job_output(vault_name, job_id, file_name, batch_size)
