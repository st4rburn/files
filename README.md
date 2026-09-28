# Files App

*Yet to be named...*

## Setup

A Dockerfile and `docker-compose.yml` are maintained in the repo and the image is available at `st4rburn/files` on (Docker Hub](https://hub.docker.com/r/st4rburn/files). These can be used as a base for setup.

By default, the share root folder is located at `/shares`. This is automatically set up by Docker, but should be mounted to a folder on the host for persistence. While configuration via environment variables should be possible, this has not been tested yet, so another mount should be created for `/app/config.toml`.

### Example Docker Command

`# docker run -it --rm -v ./config.toml:/app/config.toml,readonly -v ./shares:/shares st4rburn/files`

## Configuration

Config consists on a TOML file containing four main sections listed below: auth, main, web, and shares.

### Authentication

#### Recovery Token

```toml
[auth]
recovery_token = "<secure random string>"
```

This app allows you to specify a recovery token with full permissions over the web application. This should generally be left out of configuration, as adding one without needing to could allow an attacker access to all shares. Nevertheless, this can be a useful option for recovering info when permissions are broken and the backing filesystem is unavailable.

#### OIDC

```toml
[auth.oidc]
# Required for OIDC to work
issuer = "https://issuer_url"
client_id = "client_id_from_idp"
# Optional
scopes = "openid profile email"
groups_claim = "groups"
username_claim = "preferred_username"
# Rarely needed, fallback if automatic discovery fails
well_known_url = "https://..."
authorization_endpoint = "https://..."
token_endpoint = "https://..."
end_session_endpoint = "https://..."
jwks_uri = "https://..."
```

The primary method of authentication to the web app is designed to be OIDC. This documentation assumes knowledge of OIDC, however setup should usually be simple. An issuer URL is required, and from this the location of the `.well-known` endpoint provided by most IdPs will be calculated and used to find other relevant endpoints (the well known URL can also be specified if the app fails to find it). If this fails, these may be specified manually. The application also requires its client ID from the IdP. A client secret is not required as PKCE is used to verify the authentication.

The default claim for username is `preferred_username`, however see the [security](#Security) section below for how to configure this if your users control this claim's value. A groups claim can also be used to set permissions in shares, and scopes can be defined in case an additional scope is required to access group info.

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
