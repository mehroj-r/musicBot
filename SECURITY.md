# Security Policy

## Supported Versions

Only the latest release and the `master` branch receive security fixes.

## Reporting a Vulnerability

Please **do not** open a public issue for security problems.

Report privately through GitHub: **Security → Report a vulnerability**
(<https://github.com/mehroj-r/music-bot/security/advisories/new>).

Include what you found, how to reproduce it, and the impact you expect. You should get a reply within a few days;
once a fix is released, the advisory is published with credit unless you prefer otherwise.

Particularly relevant areas: access control (`ADMIN_IDS`, access requests, `/allow` and `/revoke`), the Yandex Music
token stored in the database, YouTube cookies in `secrets/`, the Telethon session in the data directory, and the links
users send, which yt-dlp fetches from the server.
