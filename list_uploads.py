import boto3
import argparse
import pprint


def main():
    glacier = boto3.client('glacier')
    args = parse_args()

    if args['job_type'] == 'all' or args['job_type'] == 'list-all':
        job_type = 'list-all'
    else:
        job_type = 'list-one'

    request_args = {'vaultName': args['vault_name']}
    if job_type == 'list-all':
        print('Listing all multipart uploads...')
        uploads_list = []

        more_pages = True
        while more_pages:
            response = glacier.list_multipart_uploads(**request_args)
            uploads_list.extend(response['UploadsList'])
            if 'Marker' not in response:
                more_pages = False
            else:
                request_args['marker'] = response['Marker']

        pprint.pprint(uploads_list)
    else:
        print('Listing parts in one multipart upload...')
        request_args['uploadId'] = args['upload_id']

        parts_list = []

        more_pages = True
        while more_pages:
            response = glacier.list_parts(**request_args)
            parts_list.extend(response['Parts'])
            if 'Marker' not in response:
                more_pages = False
            else:
                request_args['marker'] = response['Marker']

        pprint.pprint(parts_list)


def parse_args():
    parser = argparse.ArgumentParser(
        description='List multipart uploads and parts in an upload.')

    parser.add_argument('job_type', choices=['all', 'list-all',
                                             'one', 'list-one'],
                        help='The type of job: list all multipart uploads'
                        'or just one')
    parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault')
    parser.add_argument('-u', '--upload-id',
                        help='ID of upload to list parts')

    args = vars(parser.parse_args())

    if args['job_type'] == 'one' or args['job_type'] == 'list-one':
        if args['upload_id'] is None:
            raise ValueError('For list-one jobs, '
                             'provide job id with argument "-j".')

    return args

if __name__ == '__main__':
    main()
