import argparse
import tempfile
import tarfile
import boto3
import math
import threading
import queue
import hashlib
import binascii

q = queue.Queue()
fileblock = threading.Lock()
list_of_checksums = []


def main():
    args = parse_args()

    print('Reading file...')
    if len(args['file_name']) == 1 and '.tar' in args['file_name'][0]:
        file_to_upload = open(args['file_name'][0], mode='rb')
        print('Opened pre-tarred file.')
    else:
        print('Tarring file...')
        file_to_upload = tempfile.TemporaryFile()
        tar = tarfile.open(fileobj=file_to_upload, mode='w:xz')
        for filename in args['file_name']:
            tar.add(filename)
        tar.close()
        print('File tarred.')

    vault_name = args['vault_name']
    part_size = args['part_size'] * 1024 * 1024

    file_size = file_to_upload.seek(0, 2)

    for byte_pos in range(0, file_size, part_size):
        q.put(byte_pos)
        list_of_checksums.append(None)

    print('File size is %d bytes. Will upload in %d parts.' % (file_size, q.qsize()))

    glacier = boto3.client('glacier')
    response = glacier.initiate_multipart_upload(
        vaultName=vault_name,
        archiveDescription=args['arc_desc'],
        partSize=str(part_size)
        )
    upload_id = response['uploadId']
    print('Initiating multipart upload...')

    for i in range(args['num_threads']):
        t = threading.Thread(target=upload_part,
                             args=(vault_name, upload_id, part_size,
                                   file_to_upload, file_size))
        t.start()

    q.join()

    total_tree_hash = calculate_total_tree_hash()

    glacier.complete_multipart_upload(
        vaultName=vault_name, uploadId=upload_id,
        archiveSize=str(file_size), checksum=total_tree_hash)
    print('Completing multipart upload...')
    print('Total tree hash: %s' % total_tree_hash)
    file_to_upload.close()


def upload_part(vault_name, upload_id, part_size, fileobj, file_size):
    print('Thread starting...')
    glacier = boto3.client('glacier')
    while True:
        try:
            byte_pos = q.get(block=False)
        except queue.Empty:
            break

        fileblock.acquire()
        fileobj.seek(byte_pos)
        part = fileobj.read(part_size)
        fileblock.release()

        range_header = 'bytes {}-{}/*'.format(
            byte_pos, byte_pos + len(part) - 1)

        print('Uploading part %s...' % byte_pos)
        response = glacier.upload_multipart_part(
            vaultName=vault_name, uploadId=upload_id, range=range_header,
            body=part)
        list_of_checksums[int(byte_pos / part_size)] = response['checksum']

        q.task_done()
    print('Thread done.')


def calculate_total_tree_hash():
    tree = list_of_checksums[:]
    while len(tree) > 1:
        parent = []
        for i in range(0, len(tree), 2):
            if i < len(tree) - 1:
                part1 = binascii.unhexlify(tree[i])
                part2 = binascii.unhexlify(tree[i + 1])
                parent.append(hashlib.sha256(part1 + part2).hexdigest())
            else:
                parent.append(tree[i])
        tree = parent
    return tree[0]


def parse_args():
    parser = argparse.ArgumentParser(
        description='Upload a file to glacier using multipart upload.')

    parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    parser.add_argument('-f', '--file-name', nargs='+',
                        help='The file or directroy name on your local '
                        'filesystem to upload')
    parser.add_argument('-d', '--arc-desc', default='',
                        metavar='ARCHIVE_DESCRIPTION',
                        help='The archive description')
    parser.add_argument('-p', '--part-size', type=int, default=8,
                        help='The part size for multipart upload, in '
                        'megabytes (e.g. 1, 2, 4, 8) default: 8')
    parser.add_argument('-t', '--num-threads', type=int, default=5,
                        help='The amount of concurrent threads (default: 5)')

    args = vars(parser.parse_args())

    if not math.log2(args['part_size']).is_integer():
        raise ValueError('part-size must be a power of 2')
    if args['part_size'] < 1 or args['part_size'] > 4096:
        raise ValueError('part-size must be more than 1 MB '
                         'and less than 4096 MB')

    return args

if __name__ == '__main__':
    main()
