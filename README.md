# glacier-upload

A simple script to upload files to an AWS Glacier vault.

## Installation

```
$ pip install glacier_upload
```

## Usage

There are eight scripts available for use.

- `glacier_upload`: Upload files to glacier (pre-archive if necessary) using multithreaded multipart upload.
- `list_all_glacier_uploads`: List all glacier uploads currently pending.
- `list_parts_in_upload`: List all parts that have been uploaded so far in a multipart upload batch.
- `init_archive_retrieval`: Initiate retrieval for a specific archive.
- `init_inventory_retrieval`: Initiate inventory retrieval for the whole vault.
- `get_glacier_job_output`: Get the output of a job (archive retrieval or inventory retrieval)
- `abort_glacier_upload`: Abort a multipart glacier upload.
- `delete_glacier_archive`: Delete a glacier archive.

For options and arguments, invoke the corresponding command with `--help`.

### How `glacier_upload` works

The script will read a file (or more), archive it (them) if it isn't already an archive, split the file into chunks, and spawn a number of threads that will upload the chunks in parallel. Note that it will not read the entire file into memory, but only as it processes the chunks.

## Dependencies

The script has only two dependencies: [boto3](https://github.com/boto/boto3/) and [click](http://click.pocoo.org).

It is built to run on Python 3.5 and newer. Python 2 is not supported.

## Contributing

Contributions and/or bug fixes are welcome! Just fork, make a topic branch, format the code using [black](https://github.com/python/black) `--line-length=80` and submit a PR. Don't forget to add your name in CONTRIBUTORS.

A good place to start is the TODO file.
