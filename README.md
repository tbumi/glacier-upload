# glacier-upload

A simple script to upload files to an AWS Glacier vault.

## Background

I wanted to backup my files to Amazon Glacier. But apparently Amazon Glacier usage is not that straightforward. So I whipped up this script and thought it might be useful for someone somewhere someday (maybe never but who cares).

## Features

You can execute the main python script from the command line. Be sure to provide it with some arguments, namely:

- `-v` or `--vault-name`: the name of the AWS Glacier vault you want to upload to. You can create a vault from the AWS Web Console.
- `-f` or `--file-name`: the name of the file(s) you want to insert in the archive. You can specify one or more files, and they will be automatically archived in a tar and compressed with the [LZMA](https://en.wikipedia.org/wiki/Lempel%E2%80%93Ziv%E2%80%93Markov_chain_algorithm) compression algorithm. If you specify only one file and the filename contains `.tar`, it will be regarded as already archived and will not be rearchived/recompressed.
- `-d` or `--arc-desc`: provide a description for your archive. This will be very useful for retrieval of your archive later, as the original filename will be lost in Glacier.
- `-p` or `--part-size`: the archive will be split into chunks before uploading. You can choose the chunk size in MB, but it has to be a multiply of a power of two (e.g. 2, 4, 8, 16, 32, and so on), with a minimum of 1, and a maximum of 4096. Defaults to 8.
- `-t` or `--num-threads`: the number of threads used for uploading. Defaults to 5.

The required values are `vault-name` and `file-name`. `file-name` can be one or more files.

Example invocation:

```
python main.py -v some-vault -f file01.txt file2.jpg file3.png -d "A backup of my files"
```

## How it works

The script will read a file (or more), archive it (them) if it isn't already an archive, split the file into chunks, and spawn a number of threads that will upload the chunks in parallel. Note that it will not read the entire file into memory, but only as it processes the chunks.

## Dependencies

The script has only one dependency: [boto3](https://github.com/boto/boto3/). It is built to run on Python 3 (tested on Python 3.5). I have no plans to support Python 2.

## Roadmap

If I have the time and willpower (or maybe you could send me a PR ;) ), there is always room for development:

- Add ability to verify multipart uploads by requesting a list of parts and checking them
- Add ability to list/cancel in-progress uploads
- Add ability to resume uploads
- Add progress indication for archiving
