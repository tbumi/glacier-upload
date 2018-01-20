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

import binascii
import concurrent.futures
import hashlib
import math
import os.path
import sys
import tarfile
import tempfile
import threading

import boto3
import click

MAX_ATTEMPTS = 10

fileblock = threading.Lock()
glacier = boto3.client('glacier')


@click.command()
@click.option('-v', '--vault-name', required=True,
              help='The name of the vault to upload to')
@click.option('-f', '--file-name', required=True, multiple=True,
              help='The file or directory name on your local '
              'filesystem to upload')
@click.option('-d', '--arc-desc', default='',
              metavar='ARCHIVE_DESCRIPTION',
              help='The archive description to help identify archives later')
@click.option('-p', '--part-size', type=int, default=8,
              help='The part size for multipart upload, in '
              'megabytes (e.g. 1, 2, 4, 8) default: 8')
@click.option('-t', '--num-threads', type=int, default=5,
              help='The amount of concurrent threads (default: 5)')
@click.option('-u', '--upload-id',
              help='Optional upload id, if provided then will '
              'resume upload.')
def upload(vault_name, file_name, arc_desc, part_size, num_threads, upload_id):
    if not math.log2(part_size).is_integer():
        raise ValueError('part-size must be a power of 2')
    if part_size < 1 or part_size > 4096:
        raise ValueError('part-size must be more than 1 MB '
                         'and less than 4096 MB')

    click.echo('Reading file...')
    if len(file_name) > 1 or os.path.isdir(file_name[0]):
        click.echo('Tarring file...')
        file_to_upload = tempfile.TemporaryFile()
        tar = tarfile.open(fileobj=file_to_upload, mode='w:xz')
        for filename in file_name:
            tar.add(filename)
        tar.close()
        click.echo('File tarred.')
    else:
        file_to_upload = open(file_name[0], mode='rb')
        click.echo('Opened single file.')

    part_size = part_size * 1024 * 1024

    file_size = file_to_upload.seek(0, 2)

    if file_size < 4096:
        click.echo('File size is less than 4 MB. Uploading in one request...')

        response = glacier.upload_archive(
            vaultName=vault_name,
            archiveDescription=arc_desc,
            body=file_to_upload)

        click.echo('Uploaded.')
        click.echo('Glacier tree hash: %s' % response['checksum'])
        click.echo('Location: %s' % response['location'])
        click.echo('Archive ID: %s' % response['archiveId'])
        click.echo('Done.')
        file_to_upload.close()
        return

    job_list = []
    list_of_checksums = []

    if upload_id is None:
        click.echo('Initiating multipart upload...')
        response = glacier.initiate_multipart_upload(
            vaultName=vault_name,
            archiveDescription=arc_desc,
            partSize=str(part_size)
        )
        upload_id = response['uploadId']

        for byte_pos in range(0, file_size, part_size):
            job_list.append(byte_pos)
            list_of_checksums.append(None)

        num_parts = len(job_list)
        click.echo('File size is {} bytes. Will upload in {} parts.'.format(file_size, num_parts))
    else:
        click.echo('Resuming upload...')

        click.echo('Fetching already uploaded parts...')
        response = glacier.list_parts(
            vaultName=vault_name,
            uploadId=upload_id
        )
        parts = response['Parts']
        part_size = response['PartSizeInBytes']
        while 'Marker' in response:
            click.echo('Getting more parts...')
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
        with click.progressbar(parts, label='Verifying uploaded parts') as bar:
            for part_data in bar:
                byte_start = int(part_data['RangeInBytes'].partition('-')[0])
                file_to_upload.seek(byte_start)
                part = file_to_upload.read(part_size)
                checksum = calculate_tree_hash(part, part_size)

                if checksum == part_data['SHA256TreeHash']:
                    job_list.remove(byte_start)
                    part_num = byte_start // part_size
                    list_of_checksums[part_num] = checksum

    click.echo('Spawning threads...')
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_threads) as executor:
        futures_list = {executor.submit(
            upload_part, job, vault_name, upload_id, part_size, file_to_upload,
            file_size, num_parts): job // part_size for job in job_list}
        done, not_done = concurrent.futures.wait(
            futures_list, return_when=concurrent.futures.FIRST_EXCEPTION)
        if len(not_done) > 0:
            # an exception occured
            for future in not_done:
                future.cancel()
            for future in done:
                e = future.exception()
                if e is not None:
                    click.echo('Exception occured: %r' % e)
            click.echo('Upload not aborted. Upload id: %s' % upload_id)
            click.echo('Exiting.')
            file_to_upload.close()
            sys.exit(1)
        else:
            # all threads completed without raising
            for future in done:
                job_index = futures_list[future]
                list_of_checksums[job_index] = future.result()

    if len(list_of_checksums) != num_parts:
        click.echo('List of checksums incomplete. Recalculating...')
        list_of_checksums = []
        for byte_pos in range(0, file_size, part_size):
            part_num = int(byte_pos / part_size)
            click.echo('Checksum %s of %s...' % (part_num + 1, num_parts))
            file_to_upload.seek(byte_pos)
            part = file_to_upload.read(part_size)
            list_of_checksums.append(calculate_tree_hash(part, part_size))

    total_tree_hash = calculate_total_tree_hash(list_of_checksums)

    click.echo('Completing multipart upload...')
    response = glacier.complete_multipart_upload(
        vaultName=vault_name, uploadId=upload_id,
        archiveSize=str(file_size), checksum=total_tree_hash)
    click.echo('Upload successful.')
    click.echo('Calculated total tree hash: %s' % total_tree_hash)
    click.echo('Glacier total tree hash: %s' % response['checksum'])
    click.echo('Location: %s' % response['location'])
    click.echo('Archive ID: %s' % response['archiveId'])
    click.echo('Done.')
    file_to_upload.close()


def upload_part(byte_pos, vault_name, upload_id, part_size, fileobj, file_size,
                num_parts):
    fileblock.acquire()
    fileobj.seek(byte_pos)
    part = fileobj.read(part_size)
    fileblock.release()

    range_header = 'bytes {}-{}/{}'.format(
        byte_pos, byte_pos + len(part) - 1, file_size)
    part_num = byte_pos // part_size
    percentage = part_num / num_parts

    click.echo('Uploading part {0} of {1}... ({2:.2%})'.format(
        part_num + 1, num_parts, percentage))

    for i in range(MAX_ATTEMPTS):
        try:
            response = glacier.upload_multipart_part(
                vaultName=vault_name, uploadId=upload_id,
                range=range_header, body=part)
            checksum = calculate_tree_hash(part, part_size)
            if checksum != response['checksum']:
                click.echo('Checksums do not match. Will try again.')
                continue

            # if everything worked, then we can break
            break
        except:
            click.echo('Upload error:', sys.exc_info()[0])
            click.echo('Trying again. Part {0}'.format(part_num + 1))
    else:
        click.echo('After multiple attempts, still failed to upload part')
        click.echo('Exiting.')
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


if __name__ == '__main__':
    upload()
