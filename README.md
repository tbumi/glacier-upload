# glacier-upload

A helper tool to upload and manage archives in AWS Glacier Vaults

## Installation

Minimum required Python version is 3.9. To install, run this in your terminal:

```
$ pip install glacier_upload
```

## Quickstart

AWS Glacier is a cloud storage service that can store your files long term for a relatively cheap price. To upload an archive to AWS Glacier vault, follow these steps:

1. Create an AWS account, if you haven't already.
1. Create an AWS Glacier vault from the AWS Management Console
1. Run `glacier-upload -d <archive_description> <vault_name> <file_name(s)>`

### Available Scripts

There are eight scripts available for use.

- `glacier-upload`: Upload files to glacier (pre-archive if necessary) using multithreaded multipart upload.

- `glacier-list-all-uploads`: List all glacier uploads currently pending in a vault.
- `glacier-list-parts-in-upload`: List all parts that have been uploaded so far as a part of a multipart upload batch.
- `glacier-abort-upload`: Abort a multipart glacier upload.
- `glacier-init-archive-retrieval`: Initiate retrieval for a specific archive.
- `glacier-init-inventory-retrieval`: Initiate inventory retrieval for the whole vault.
- `glacier-delete-archive`: Delete a glacier archive.

For options and arguments, invoke the corresponding command with `--help`.

### How `glacier-upload` works

The script will read a file (or more), archive them if it isn't already an archive, split the file into chunks, and spawn a number of threads that will upload the chunks in parallel. Note that it will not read the entire file into memory, but only as it processes the chunks.

## Contributing

Contributions and/or bug fixes are welcome! Just fork, make a topic branch, make your changes, and submit a PR.

### Development Requirements

Before committing to this repo, setup [poetry](https://python-poetry.org/) on your local machine, then run these commands to setup your environment:

```sh
poetry install
pre-commit install
```

All code is formatted with [black](https://github.com/psf/black).
