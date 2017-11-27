import boto3
import argparse


def main():
    glacier = boto3.client('glacier')
    args = parse_args()

    print('Sending delete archive request...')

    response = glacier.delete_archive(
        vaultName=args['vault_name'],
        archiveId=args['archive_id'])

    print('Delete archive request sent. Response:\n%s' % response)

def parse_args():
    parser = argparse.ArgumentParser(
        description='Delete an archive from glacier.')

    parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    parser.add_argument('-a', '--archive-id', required=True,
                        help='ID of the archive to retrieve')

    args = vars(parser.parse_args())
    return args

if __name__ == '__main__':
    main()
