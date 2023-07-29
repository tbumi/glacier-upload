# glacier-upload

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![pypi](https://img.shields.io/pypi/v/glacier_upload)](https://pypi.org/project/glacier_upload/)
[![License-GPLv3](https://img.shields.io/github/license/tbumi/glacier-upload)](https://github.com/tbumi/glacier-upload/blob/main/LICENSE)

A helper tool to upload and manage archives in
[Amazon S3 Glacier](https://docs.aws.amazon.com/amazonglacier/latest/dev/introduction.html)
Vaults. Amazon S3 Glacier is a cloud storage service that is optimized for long
term storage for a relatively cheap price. NOT to be confused with Amazon S3
with Glacier (Instant Retrieval, Flexible Retrieval, and Deep Archive) tier
storage, which uses the S3 API and does not deal with vaults and archives.

## Installation

Minimum required Python version is 3.9. To install, run this in your terminal:

```
$ pip install glacier_upload
```

## Usage

### Prerequisites

To upload an archive to Amazon S3 Glacier vault, ensure you have:

- Created an AWS account
- Created an Amazon S3 Glacier vault from the AWS CLI tool or the Management
  Console

### Uploading an archive

An upload can be performed by running `glacier upload` followed by the vault
name and the file name(s) that you want to upload.

```
glacier upload VAULT_NAME FILE_NAME [FILE_NAME ...]
```

`FILE_NAME` can be one or more files or directories.

The script will:

1. Read the file(s)
2. Consolidate them into a `.tar.xz` archive if multiple `FILE_NAME`s are
   specified or `FILE_NAME` is one or more directories
3. Upload the file in one go if the file is less than 100 MB in size, or
4. Split the file into chunks
5. Spawn a number of threads that will upload the chunks in parallel. Note that
   it will not read the entire file into memory, but only parts of the file as
   it processes the chunks.
6. Return the archive ID when complete. Consider saving this archive ID in a
   safe place for retrieval purposes, because Amazon Glacier does not provide a
   list of archives in realtime. See the "Requesting an inventory" section below
   for details.

There are additional options to customize your upload, such as adding a
description to the archive or configuring the number of threads or the size of
parts. Run `glacier upload --help` for more information.

If a multipart upload is interrupted in the middle (because of an exception,
interrupted manually, or other reason), the script will show you the upload ID.
That upload ID can be used to resume the upload, using the same command but
adding the `--upload-id` option, like so:

```
glacier upload --upload-id UPLOAD_ID VAULT_NAME FILE_NAME [FILE_NAME ...]
```

### Retrieving an archive

Retrieving an archive in glacier requires two steps. First, initiate a
"retrieval job" using:

```
glacier archive init-retrieval VAULT_NAME ARCHIVE_ID
```

To see a list of archive IDs in a vault, see "Requesting an inventory" below.

Then, the retrieval job will take some time to complete. Run the next step to
both check whether the job is complete and retrieve the archive if it has been
completed.

```
glacier archive get VAULT_NAME JOB_ID FILE_NAME
```

### Requesting an inventory

Vaults do not provide realtime access to a list of their contents. To know what
a vault contains, you need to request an inventory of the archive, in a similar
manner to retrieving an archive. To initiate an inventory, run:

```
glacier inventory init-retrieval VAULT_NAME
```

Then, the inventory job will take some time to complete. Run the next step to
both check whether the job is complete and retrieve the inventory if it has been
completed.

```
glacier inventory get VAULT_NAME JOB_ID
```

### Deleting an archive, deleting an upload job, creating/deleting a vault, etc.

All jobs other than uploading an archive and requesting/downloading an inventory
or archive can be done using the AWS CLI. Those functionalities are not
implemented here to avoid duplication of work, and minimize maintenance efforts
of this package.

## Contributing

Contributions and/or bug fixes are welcome! Just make sure you've read the below
requirements, then feel free to fork, make a topic branch, make your changes,
and submit a PR.

### Development Requirements

Before committing to this repo, install [poetry](https://python-poetry.org/) on
your local machine, then run these commands to setup your environment:

```sh
poetry install
pre-commit install
```

All code is formatted with [black](https://github.com/psf/black). Consider
installing an integration for it in your favourite text editor.
