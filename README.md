# Files App

*Yet to be named...*

## Setup

A Dockerfile and `docker-compose.yml` are maintained in the repo and the image is available at `st4rburn/files`. These can be used as a base for setup.

By default, the share root folder is located at `/shares`. This is automatically set up by Docker, but should be mounted to a folder on the host for persistence. While configuration via environment variables should be possible, this has not been tested yet, so another mount should be created for `/app/config.toml`.

### Example Docker Command

`# docker run -it --rm -v ./config.toml:/app/config.toml,readonly -v ./shares:/shares st4rburn/files`

## Security

### OIDC Usernames

If your authentication backend allows users to change their usernames, you should set `username_claim` to `"sub"` in OIDC configuration and write ACL rules using the user's UUID instead. By default, this value is set to `"preferred_username"` for ACL readability and ease of use as this value is static in most cases.

Generally when using OIDC, it would be recommended to assign access based on groups/roles, but if specific users must be assigned particular shares without groups it is better to use `"sub"` where a user may be able to change their username.

It should also be noted that any dynamic shares created under one username claim will not transfer to another, and migrating from `"preferred_username"` to `"sub"` may cause a user to lose access to their files if the folders are not renamed.

### Known Flaws

It is currently possible to see that shares you can't access exist when they're not below dotted names (or the user has dotfile permissions). You can't list, download, or perform any other operation but you can see they exist.
Eventually this should be fixed but this is not a high priority.
