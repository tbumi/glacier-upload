- Unit tests
- https://help.github.com/en/articles/setting-guidelines-for-repository-contributors

- Support multpart download of archives like in #25
- Add progress indication for archiving
- implement auto-retry on multipart upload failure

  - it should ask the user for confirmation to continue
  - implement a flag to auto retry without confirmation

- Optionally integrate with DynamoDB to store archive IDs and metadata