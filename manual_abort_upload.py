import boto3
import argparse


def main():
    glacier = boto3.client('glacier')
    args = parse_args()

    print('Aborting upload...')
    glacier.abort_multipart_upload(
        vaultName=args['vault-name'],
        uploadId=args['upload-id']
    )

    print('Aborted.')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Manually abort an upload.')

    parser.add_argument('vault-name',
                        help='The name of the vault')
    parser.add_argument('upload-id',
                        help='The upload id')

    args = vars(parser.parse_args())

    return args

if __name__ == '__main__':
    main()
