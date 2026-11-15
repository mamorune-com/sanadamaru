"""Decoy doors and their contents (all fake).

Rules for writing door contents (docs/en/lines.md):
- No real keys, settings or user data. No names or email addresses that look like real people.
- Plain text only. No scripts and no files that get heavy when opened (such as zip bombs).
- The same content on every read. Random values or timestamps would change between reads and give the decoy away.
- Embed bait keys with key(field_name). Each field gets its own key, so you learn which kind of door (marker) and which field a key came from.
- Only use paths that real users and pages never open. A path that collides with a real endpoint records real users.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Dict

KeyMaker = Callable[..., str]
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


@dataclass(frozen=True)
class Door:
    """A decoy door.

    marker: a short name for the kind of door (lowercase letters, digits, `_`, `-`). Used in records and to match bait keys.
    Doors that share a marker share bait keys.
    content_type: the content type to return (for example `text/plain; charset=utf-8`).
    template: a function that builds the content. Calling its argument key(field_name) returns that field's bait key.
    """

    marker: str
    content_type: str
    template: Callable[[KeyMaker], str]

    def __post_init__(self) -> None:
        if not isinstance(self.marker, str) or not NAME_PATTERN.fullmatch(self.marker):
            raise ValueError(f"door marker must be up to 32 lowercase letters, digits, _ or -: {self.marker!r}")
        if not self.content_type or any(c in self.content_type for c in "\r\n"):
            raise ValueError(f"invalid content_type: {self.content_type!r}")
        if not callable(self.template):
            raise TypeError("template must be a function that builds the content")


TEXT = "text/plain; charset=utf-8"
HTML = "text/html; charset=utf-8"
JSON = "application/json"


def _env(key: KeyMaker) -> str:
    return (
        "APP_NAME=web\n"
        "APP_ENV=production\n"
        "APP_DEBUG=false\n"
        "APP_URL=https://web.internal\n"
        "\n"
        "DB_CONNECTION=pgsql\n"
        "DB_HOST=10.20.0.15\n"
        "DB_PORT=5432\n"
        "DB_DATABASE=web_prod\n"
        "DB_USERNAME=web\n"
        f"DB_PASSWORD={key('db')}\n"
        "\n"
        f"SECRET_KEY={key('secret')}\n"
        f"INTERNAL_API_KEY={key('api')}\n"
        "SMTP_HOST=smtp.internal\n"
        "SMTP_PORT=587\n"
    )


def _git_config(key: KeyMaker) -> str:
    return (
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tfilemode = true\n"
        "\tbare = false\n"
        "\tlogallrefupdates = true\n"
        '[remote "origin"]\n'
        f"\turl = https://ci-deploy:{key('deploy')}@git.internal/web/web.git\n"
        "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        '[branch "main"]\n'
        "\tremote = origin\n"
        "\tmerge = refs/heads/main\n"
    )


def _git_head(key: KeyMaker) -> str:
    return "ref: refs/heads/main\n"


def _wp_login(key: KeyMaker) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en-US"><head><meta charset="UTF-8"><title>Log In</title></head>\n'
        '<body class="login"><div id="login">\n'
        '<form name="loginform" id="loginform" action="/wp-login.php" method="post">\n'
        '<p><label for="user_login">Username or Email Address</label>\n'
        '<input type="text" name="log" id="user_login" autocomplete="username"></p>\n'
        '<p><label for="user_pass">Password</label>\n'
        '<input type="password" name="pwd" id="user_pass" autocomplete="current-password"></p>\n'
        '<p class="submit"><input type="submit" name="wp-submit" id="wp-submit" value="Log In"></p>\n'
        "</form></div></body></html>\n"
    )


def _wp_config(key: KeyMaker) -> str:
    return (
        "<?php\n"
        "define( 'DB_NAME', 'wordpress' );\n"
        "define( 'DB_USER', 'wp_user' );\n"
        f"define( 'DB_PASSWORD', '{key('db')}' );\n"
        "define( 'DB_HOST', '10.20.0.21' );\n"
        "define( 'DB_CHARSET', 'utf8mb4' );\n"
        f"define( 'AUTH_KEY', '{key('auth')}' );\n"
        f"define( 'SECURE_AUTH_KEY', '{key('secure')}' );\n"
        "$table_prefix = 'wp_';\n"
        "define( 'WP_DEBUG', false );\n"
    )


def _sql_dump(key: KeyMaker) -> str:
    return (
        "--\n-- PostgreSQL database dump\n--\n\n"
        "SET statement_timeout = 0;\n"
        "SET client_encoding = 'UTF8';\n\n"
        "CREATE TABLE public.service_tokens (\n"
        "    id integer NOT NULL,\n"
        "    label text NOT NULL,\n"
        "    token text NOT NULL\n"
        ");\n\n"
        "COPY public.service_tokens (id, label, token) FROM stdin;\n"
        f"1\tbatch\t{key('batch')}\n"
        f"2\tadmin\t{key('admin')}\n"
        "\\.\n\n"
        "--\n-- PostgreSQL database dump complete\n--\n"
    )


def _actuator_env(key: KeyMaker) -> str:
    return json.dumps({
        "activeProfiles": ["prod"],
        "propertySources": [{
            "name": "Config resource 'class path resource [application-prod.yml]'",
            "properties": {
                "spring.datasource.url": {"value": "jdbc:postgresql://10.20.0.15:5432/web"},
                "spring.datasource.username": {"value": "web"},
                "spring.datasource.password": {"value": key("db")},
                "app.internal.api-key": {"value": key("api")},
            },
        }],
    }, indent=2) + "\n"


def default_doors() -> Dict[str, Door]:
    """The default doors (path -> door). Returns a new dict on every call, so you can add or remove doors freely.

    All of them are paths scanners probe first, and none of them is a real endpoint in an ordinary web app.
    If your app has a real endpoint at one of these paths, remove that door.
    """
    env = Door("env", TEXT, _env)
    git = Door("git", TEXT, _git_config)
    head = Door("git", TEXT, _git_head)
    wp = Door("wp", HTML, _wp_login)
    wpc = Door("wpconfig", TEXT, _wp_config)
    sql = Door("sql", TEXT, _sql_dump)
    act = Door("actuator", JSON, _actuator_env)
    return {
        "/.env": env,
        "/.env.local": env,
        "/.env.prod": env,
        "/.env.production": env,
        "/.env.backup": env,
        "/.env.bak": env,
        "/.env.old": env,
        "/.git/config": git,
        "/.git/HEAD": head,
        "/wp-login.php": wp,
        "/wp-admin/": wp,
        "/wp-config.php.bak": wpc,
        "/wp-config.php.old": wpc,
        "/wp-config.php~": wpc,
        "/backup.sql": sql,
        "/database.sql": sql,
        "/db.sql": sql,
        "/dump.sql": sql,
        "/actuator/env": act,
    }
