# Files App

*Yet to be named...*

## Setup

A Dockerfile and `docker-compose.yml` are maintained in the repo and the image is available at `st4rburn/files` on [Docker Hub](https://hub.docker.com/r/st4rburn/files). These can be used as a base for setup.

By default, the share root folder is located at `/shares`. This is automatically set up by Docker, but should be mounted to a folder on the host for persistence. While configuration via environment variables should be possible, this has not been tested yet, so another mount should be created for `/app/config.toml`.

### Example Docker Command

`# docker run -it --rm -v ./config.toml:/app/config.toml,readonly -v ./shares:/shares st4rburn/files`

## Configuration

Config consists on a TOML file containing four main sections listed below: [auth](#Authentication), [main](#Main), [web](#Web), and [shares](#Shares).

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

### Main

```toml
site_root = "https://files.example.com/"
share_root = "/shares"
session_secret = "<securely generated random string>"
debug = false
```

#### Site Root
Defines the base URL of the application, allowing the site to be hosted at subpaths such as 'https://example.com/files/app'. **Note that this is currently untested.**

### Share Root
The root folder for all shares on the disk (unless otherwise specified in share config). This should not be touched when using Docker as it defaults to '/shares', but other configurations may wish to change this.

### Session Secret
Used to encrypt session data, should be randomly generated and is usually 32 bytes of random data converted to hexadecimal.

### Debug
Currently unused, but will enable more verbose errors.

### Web

```toml
[web.buttons]
delete = "delete"
rename = "rename"
download = "download"
upload = "Choose File"
mkdir = "New Folder"
```

#### Web Buttons
Defines text found on default control buttons, allowing for easier modification and styling.

```toml
[web]
api_path = "/_"
default_style = true
extra_styles = []
default_script = true
extra_scripts = []
extra_head = "<script>some injected JS</script>"
```

#### API Path
Where supporting API routes are found, generally does not need changing but importantly a share with this same path may introduce bugs.

#### Default Style / Script
Whether to use the default CSS / JavaScript bundled with the app. The recommendation is to always keep the JavaScript enabled, but CSS can be disabled if a style overhaul is being done in a theme.

#### Extra Styles / Scripts
The locations of any additional styles or scripts to load relative to the app's 'static/extra' folder. CSS is stored in 'static/extra/css' and JavaScript in 'static/extra/js'. In Docker, this means the folder to mount would be '/app/static/extra', and CSS and JS would be stored in 'css' and 'js' subfolders respectively.

#### Extra Head
Extra HTML code to inject directly into the head of every web page.

### Shares

#### Example

Shares have several options for more full customisation, a full example is shown below:

```toml
[[share]]
# Share in the root folder
path = "/documents"
# Display name / title
title = "Documents"
real = "/mnt/sda1/documents"
# Permissions - as granular as possible:
#   l - list (but not download)
#   d - download (but not list)
#   u - upload
#   r - remove / delete
#   m - move
#   . - see hidden files in list
#   * - all
[share.perms.group]
admin = "*"
documents_owner = "ldur"
[share.perms.user]
ALL = "l"
AUTHED = "d"
```

The above example defines a share called 'Documents', at path '/documents' in the main app. This means the share will be visible to users who can access it from '/', the main page. While most shares will have their files located at their path below the share root path (defined in [main](#Main), and would be `<root>/documents` in this case), the usage of 'real' means the files for this share are stored at `/mnt/sda1/documents`. Shares using the 'real' option should ideally not contain any lower shares as subfolders can be overriden by these lower shares and may become inaccessible.

Permissions are explained in-depth below.

#### Permission Configuration

Permissions are divided into users and groups and specific access controls are parsed as shown above.

```toml
[share.perms.group]
admin = "*"
documents_owner = "ldur"
[share.perms.user]
ALL = "l"
AUTHED = "d"
```

This permissions section uses two groups: 'admin' and 'documents_owner'. Both of these groups would be obtained from a user's OIDC claims in a normal setup. Admin has all permissions, and documents_owner can list, download, upload, and remove (delete). Additionally, all users can list files and authenticated users can download. A user's final permissions are defined by combining all the categories they fit into. In this case, an authenticated user fits into ALL and AUTHED, gaining both the ability to list and download files. This is also stacked with groups, meaning the 'ld' in 'documents_owner' are redundant.

There are no default permissions and permissions are not inherited between shares.

#### Permission Access Levels

- LIST (`l`) - List files in a share and see the share from web panel.
- DOWNLOAD (`d`) - Download files via direct link (allowed even when list is disabled).
- UPLOAD (`u`) - Upload files to a folder, can work without list permission but the web panel currently does not support this.
- REMOVE (`d`) - Delete files from share. Does work without list, but not in the web panel.
- MOVE (`m`) - Move/rename files. Moving files between shares requires remove in the origin and upload in the destination.
- DOTFILES (`.`) - View dotfiles (files that start with `.` and would be hidden on UNIX). Only partial support currently, but this is required along with list to list dotfiles.
- ALL (`*`) - assign all permissions.
- NONE (`-`) - symbolises no permissions.

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
