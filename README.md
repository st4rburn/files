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

It is currently possible to see folders leading to shares you can't access when they're not below dotted names (or the user has dotfile permissions). It is not possible to determine the name or any information about the shares below, but it is possible to see that a share must exist there. A good solution to this issue is not currently known, and the impact is minimal, so this is a low priority issue.

If this bothers you though, mitigation is simple: a share can be created under the root share with no permissions set, and all secret shares put below this one. Due to no user having list permission on the upper share, it will not be possible to see the names of any folders below this.

```toml
[[share]]
path = "/private"
# No permissions = no one can enumerate below this

[[share]]
path = "/private/secrets"
# Allow all permissions for admin, list+download for secret viewer user
[share.perms.user]
admin = "*"
secret_viewer = "ld"
```
