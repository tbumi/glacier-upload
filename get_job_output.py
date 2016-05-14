import boto3
import argparse
import sys
import json
import pprint


def main():
    glacier = boto3.client('glacier')
    args = parse_args()

    vault_name = args['vault_name']
    job_id = args['job_id']

    print('Checking job status...')

    response = glacier.describe_job(
        vaultName=vault_name,
        jobId=job_id)

    job_status_code = response['StatusCode']

    print('Job status: %s' % job_status_code)

    if not response['Completed']:
        print('Exiting.')
        sys.exit(0)
    else:
        print('Retrieving job data...')
        response = glacier.get_job_output(
            vaultName=vault_name,
            jobId=job_id)

        if response['contentType'] == 'application/json':
            inventory_json = json.loads(response['body'].read().decode('utf-8'))
            pprint.pprint(inventory_json)
        elif response['contentType'] == 'text/csv':
            print(response['body'].read())
        else:
            with open(args['file_name'], 'xb') as file:
                file.write(response['body'].read())


def parse_args():
    parser = argparse.ArgumentParser(
        description='Get the output of a glacier job.')

    parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    parser.add_argument('-j', '--job-id', required=True,
                        help='Job ID')
    parser.add_argument('-f', '--file-name', default='glacier_archive.tar.xz',
                        help='File name of archive to be saved, '
                             'if the job is an archive-retrieval')

    args = vars(parser.parse_args())

    return args

if __name__ == '__main__':
    main()
