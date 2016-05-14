import boto3
import argparse


def main():
    glacier = boto3.client('glacier')
    args = parse_args()

    if args['job_type'] == 'inv' or args['job_type'] == 'inventory-retrieval':
        job_type = 'inventory-retrieval'
    else:
        job_type = 'archive-retrieval'

    job_params = {
        'Type': job_type,
    }

    if args['description'] is not None:
        job_params['Description'] = args['description']

    if job_type == 'archive-retrieval':
        job_params['ArchiveId'] = args['archive_id']
    else:
        job_params['Format'] = args['format']

    print('Sending job initiation request...')

    response = glacier.initiate_job(
        vaultName=args['vault_name'],
        jobParameters=job_params)

    print('Job initiation request recieved. Job ID: %s' % response['jobId'])


def parse_args():
    parser = argparse.ArgumentParser(
        description='Initiate a glacier job.')

    parser.add_argument('job_type', choices=['arc', 'archive-retrieval',
                                             'inv', 'inventory-retrieval'],
                        help='The type of job: archive-retrieval or '
                             'inventory-retrieval')
    parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    parser.add_argument('-f', '--format', default='JSON', choices=['CSV', 'JSON'],
                        help='Format to request from glacier')
    parser.add_argument('-d', '--description',
                        help='Description of this job (optional)')
    parser.add_argument('-a', '--archive-id',
                        help='ID of the archive to retrieve')

    args = vars(parser.parse_args())

    if args['job_type'] == 'arc' or args['job_type'] == 'archive-retrieval':
        if args['archive_id'] is None:
            raise ValueError('For archive-retrieval jobs, '
                             'provide archive id with argument "-a".')

    return args

if __name__ == '__main__':
    main()
