# A simple python script to upload files to AWS Glacier vaults.
# Copyright (C) 2016 Trapsilo P. Bumi tbumi@thpd.io
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import binascii
import boto3
import concurrent.futures
import hashlib
import math
import sys
import tarfile
import tempfile
import threading
import json
import pprint

fileblock = threading.Lock()
glacier = boto3.client('glacier')
MAX_ATTEMPTS = 10


def upload(args):
    args = vars(args)
    if not math.log2(args['part_size']).is_integer():
        raise ValueError('part-size must be a power of 2')
    if args['part_size'] < 1 or args['part_size'] > 4096:
        raise ValueError('part-size must be more than 1 MB '
                         'and less than 4096 MB')

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

    if file_size < 4096:
        print('File size is less than 4 MB. Uploading in one request...')

        response = glacier.upload_archive(
            vaultName=vault_name,
            archiveDescription=args['arc_desc'],
            body=file_to_upload)

        print('Uploaded.')
        print('Glacier tree hash: %s' % response['checksum'])
        print('Location: %s' % response['location'])
        print('Archive ID: %s' % response['archiveId'])
        print('Done.')
        file_to_upload.close()
        return

    job_list = []
    list_of_checksums = []

    if args['upload_id'] is None:
        print('Initiating multipart upload...')
        response = glacier.initiate_multipart_upload(
            vaultName=vault_name,
            archiveDescription=args['arc_desc'],
            partSize=str(part_size)
            )
        upload_id = response['uploadId']

        for byte_pos in range(0, file_size, part_size):
            job_list.append(byte_pos)
            list_of_checksums.append(None)

        num_parts = len(job_list)
        print('File size is %d bytes. Will upload in %d parts.' %
              (file_size, num_parts))
    else:
        print('Resuming upload...')
        upload_id = args['upload_id']

        print('Fetching already uploaded parts...')
        response = glacier.list_parts(
            vaultName=vault_name,
            uploadId=upload_id
        )
        parts = response['Parts']
        part_size = response['PartSizeInBytes']
        while 'Marker' in response:
            print('Getting more parts...')
            response = glacier.list_parts(
                vaultName=vault_name,
                uploadId=upload_id,
                marker=response['Marker']
            )
            parts.extend(response['Parts'])

        for byte_pos in range(0, file_size, part_size):
            job_list.append(byte_pos)
            list_of_checksums.append(None)
        num_parts = len(job_list)

        for part_data in parts:
            byte_start = int(part_data['RangeInBytes'].partition('-')[0])
            sha256_treehash = part_data['SHA256TreeHash']

            part_num = int(byte_start / part_size)
            print('Checking part %s of %s...' % (part_num + 1, len(parts)))

            file_to_upload.seek(byte_start)
            part = file_to_upload.read(part_size)
            checksum = calculate_tree_hash(part, part_size)

            if checksum == sha256_treehash:
                print('Checksum match. Removing from job list.')
                job_list.remove(byte_start)
                list_of_checksums[part_num] = checksum
            else:
                print('Checksum mismatch. Not removing.')

    print('Spawning threads...')
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=args['num_threads']) as executor:
        futures_list = {executor.submit(
            upload_part, job, vault_name, upload_id, part_size, file_to_upload,
            file_size, num_parts): int(job / part_size) for job in job_list}
        done, not_done = concurrent.futures.wait(
            futures_list, return_when=concurrent.futures.FIRST_EXCEPTION)
        if len(not_done) > 0:
            # an exception occured
            for future in not_done:
                future.cancel()
            for future in done:
                e = future.exception()
                if e is not None:
                    print('Exception occured: %r' % e)
            print('Upload not aborted. Upload id: %s' % upload_id)
            print('Exiting.')
            file_to_upload.close()
            sys.exit(1)
        else:
            # all threads completed without raising
            for future in done:
                job_index = futures_list[future]
                list_of_checksums[job_index] = future.result()

    if len(list_of_checksums) != num_parts:
        print('List of checksums incomplete. Recalculating...')
        list_of_checksums = []
        for byte_pos in range(0, file_size, part_size):
            part_num = int(byte_pos / part_size)
            print('Checksum %s of %s...' % (part_num + 1, num_parts))
            file_to_upload.seek(byte_pos)
            part = file_to_upload.read(part_size)
            list_of_checksums.append(calculate_tree_hash(part, part_size))

    total_tree_hash = calculate_total_tree_hash(list_of_checksums)

    print('Completing multipart upload...')
    response = glacier.complete_multipart_upload(
        vaultName=vault_name, uploadId=upload_id,
        archiveSize=str(file_size), checksum=total_tree_hash)
    print('Upload successful.')
    print('Calculated total tree hash: %s' % total_tree_hash)
    print('Glacier total tree hash: %s' % response['checksum'])
    print('Location: %s' % response['location'])
    print('Archive ID: %s' % response['archiveId'])
    print('Done.')
    file_to_upload.close()


def upload_part(byte_pos, vault_name, upload_id, part_size, fileobj, file_size,
                num_parts):
    fileblock.acquire()
    fileobj.seek(byte_pos)
    part = fileobj.read(part_size)
    fileblock.release()

    range_header = 'bytes {}-{}/{}'.format(
        byte_pos, byte_pos + len(part) - 1, file_size)
    part_num = int(byte_pos / part_size)
    percentage = part_num/num_parts

    print('Uploading part {0} of {1}... ({2:.2%})'.format(
        part_num + 1, num_parts, percentage))

    for i in range(MAX_ATTEMPTS):
        try:
            response = glacier.upload_multipart_part(
                vaultName=vault_name, uploadId=upload_id, range=range_header,
                body=part)
            checksum = calculate_tree_hash(part, part_size)
            if checksum != response['checksum']:
                print('Checksums do not match. Will try again.')
                continue

            # if everything worked, then we can break
            break
        except:
            print('Upload error:', sys.exc_info()[0])
            print('Trying again. Part {0}'.format(part_num + 1))
    else:
        print('After multiple attempts, still failed to upload part')
        print('Exiting.')
        sys.exit(1)

    del part
    return checksum


def calculate_tree_hash(part, part_size):
    checksums = []
    upper_bound = min(len(part), part_size)
    step = 1024 * 1024  # 1 MB
    for chunk_pos in range(0, upper_bound, step):
        chunk = part[chunk_pos:chunk_pos+step]
        checksums.append(hashlib.sha256(chunk).hexdigest())
        del chunk
    return calculate_total_tree_hash(checksums)


def calculate_total_tree_hash(list_of_checksums):
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

def get_job_output(args):
    args = vars(args)
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

def initiate_job(args):
    args = vars(args)
    if args['job_type'] == 'arc' or args['job_type'] == 'archive-retrieval':
        if args['archive_id'] is None:
            raise ValueError('For archive-retrieval jobs, '
                             'provide archive id with argument "-a".')

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

def list_uploads(args):
    args = vars(args)
    if args['job_type'] == 'one' or args['job_type'] == 'list-one':
        if args['upload_id'] is None:
            raise ValueError('For list-one jobs, '
                             'provide job id with argument "-j".')

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

def manual_abort_upload(args):
    args = vars(args)
    print('Aborting upload...')
    glacier.abort_multipart_upload(
        vaultName=args['vault-name'],
        uploadId=args['upload-id']
    )

    print('Aborted.')

def delete(args):
    args = vars(args)
    print('Sending delete archive request...')
    response = glacier.delete_archive(
        vaultName=args['vault_name'],
        archiveId=args['archive_id'])
    print('Delete archive request sent. Response:\n%s' % response)


def main():
    parser = argparse.ArgumentParser(
        description='A simple script to upload files to an AWS Glacier vault.')
    subparsers = parser.add_subparsers()

    upload_parser = subparsers.add_parser('upload',
        description='Upload a file to glacier using multipart upload.')
    upload_parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    upload_parser.add_argument('-f', '--file-name', nargs='+',
                        help='The file or directory name on your local '
                        'filesystem to upload')
    upload_parser.add_argument('-d', '--arc-desc', default='',
                        metavar='ARCHIVE_DESCRIPTION',
                        help='The archive description')
    upload_parser.add_argument('-p', '--part-size', type=int, default=8,
                        help='The part size for multipart upload, in '
                        'megabytes (e.g. 1, 2, 4, 8) default: 8')
    upload_parser.add_argument('-t', '--num-threads', type=int, default=5,
                        help='The amount of concurrent threads (default: 5)')
    upload_parser.add_argument('-u', '--upload-id',
                        help='Optional upload id, if provided then will '
                              'resume upload.')
    upload_parser.set_defaults(func=upload)

    get_job_output_parser = subparsers.add_parser('get_job_output',
        description='Get the output of a glacier job.')
    get_job_output_parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    get_job_output_parser.add_argument('-j', '--job-id', required=True,
                        help='Job ID')
    get_job_output_parser.add_argument('-f', '--file-name', default='glacier_archive.tar.xz',
                        help='File name of archive to be saved, '
                             'if the job is an archive-retrieval')
    get_job_output_parser.set_defaults(func=get_job_output)

    initiate_job_parser = subparsers.add_parser('initiate_job',
        description='Initiate a glacier job.')
    initiate_job_parser.add_argument('job_type', choices=['arc', 'archive-retrieval',
                                             'inv', 'inventory-retrieval'],
                        help='The type of job: archive-retrieval or '
                             'inventory-retrieval')
    initiate_job_parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    initiate_job_parser.add_argument('-f', '--format', default='JSON', choices=['CSV', 'JSON'],
                        help='Format to request from glacier')
    initiate_job_parser.add_argument('-d', '--description',
                        help='Description of this job (optional)')
    initiate_job_parser.add_argument('-a', '--archive-id',
                        help='ID of the archive to retrieve')
    initiate_job_parser.set_defaults(func=initiate_job)

    list_uploads_parser = subparsers.add_parser('list_uploads',
        description='List multipart uploads and parts in an upload.')
    list_uploads_parser.add_argument('job_type', choices=['all', 'list-all',
                                             'one', 'list-one'],
                        help='The type of job: list all multipart uploads'
                        'or just one')
    list_uploads_parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault')
    list_uploads_parser.add_argument('-u', '--upload-id',
                        help='ID of upload to list parts')
    list_uploads_parser.set_defaults(func=list_uploads)

    manual_abort_upload_parser = subparsers.add_parser('manual_abort_upload',
        description='Manually abort an upload.')
    manual_abort_upload_parser.add_argument('vault-name',
                        help='The name of the vault')
    manual_abort_upload_parser.add_argument('upload-id',
                        help='The upload id')
    manual_abort_upload_parser.set_defaults(func=manual_abort_upload)

    delete_parser = subparsers.add_parser('delete')
    delete_parser.add_argument('-v', '--vault-name', required=True,
                        help='The name of the vault to upload to')
    delete_parser.add_argument('-a', '--archive-id', required=True,
                        help='ID of the archive to retrieve')
    delete_parser.set_defaults(func=delete)

    args = parser.parse_args()
    if len(vars(args)) == 0:
        parser.print_help()
    else:
        args.func(args)

if __name__ == '__main__':
    main()
