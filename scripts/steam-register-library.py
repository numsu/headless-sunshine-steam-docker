#!/usr/bin/env python3
"""Register the shared Steam library folder in the Steam client.

The current Steam client keeps its library folder list in
~/.steam/debian-installation/config/libraryfolders.vdf and a copy in the
legacy location ~/.steam/debian-installation/steamapps/libraryfolders.vdf.
On load it tries the legacy copy first and falls back to the config one,
so both are kept in sync by this script.

This makes sure /games/SteamLibrary is registered so users do not have to
add it by hand in Steam settings.

The client requires its own install directory to always be present in the
list; if it is missing, the client rewrites the file on first launch and
drops any foreign entries that do not pass validation. So a fresh file is
seeded with the install directory plus the shared library, and the shared
library is given a plausible contentid and a steamapps/ subdirectory (the
client also creates that) so it survives validation.

Safety rules:
  * Idempotent: an already registered folder leaves the file untouched.
  * A file with an unrecognized structure is left untouched.
  * The legacy copy is only appended to when it exists; it is never
    created, because the client manages that location itself.
  * Intended to run at boot only, while no Steam process is running.
"""

import os
import pwd
import random
import re
import sys
import tempfile

GAMER_HOME = "/home/gamer"
STEAM_LIB = "/games/SteamLibrary"
# The client's own install directory. The client requires it to be present in
# the library list: if it is missing, the client rewrites the file on first
# launch and drops foreign entries that do not pass validation.
DEFAULT_LIB = os.path.join(GAMER_HOME, ".steam", "debian-installation")
PRIMARY_PATH = os.path.join(
    GAMER_HOME, ".steam", "debian-installation", "config", "libraryfolders.vdf"
)
LEGACY_PATH = os.path.join(
    GAMER_HOME, ".steam", "debian-installation", "steamapps", "libraryfolders.vdf"
)


def make_entry(index, path):
    # The client assigns each library a 63-bit "contentid". Observed values
    # fall in the range [2^62, 2^63); a zero contentid makes the client drop
    # the entry and replace it with its own default library on first launch.
    contentid = 0x4000000000000000 | random.getrandbits(62)
    return (
        '\t"%d"\n'
        '\t{\n'
        '\t\t"path"\t\t"%s"\n'
        '\t\t"label"\t\t""\n'
        '\t\t"contentid"\t\t"%d"\n'
        '\t\t"totalsize"\t\t"0"\n'
        '\t\t"update_clean_bytes_tally"\t\t"0"\n'
        '\t\t"time_last_update_verified"\t\t"0"\n'
        '\t\t"apps"\n'
        '\t\t{\n'
        '\t\t}\n'
        '\t}\n'
    ) % (index, path, contentid)


def registered_paths(text):
    return re.findall(r'"path"\s+"([^"]*)"', text)


def write_vdf(path, text):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    user = pwd.getpwnam("gamer")
    # The entrypoint runs as root; make sure the directory (which we may
    # just have created) is owned by gamer, or the client cannot write its
    # own files there.
    os.chown(directory, user.pw_uid, user.pw_gid)
    fd, tmp = tempfile.mkstemp(prefix=".libraryfolders.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chown(tmp, user.pw_uid, user.pw_gid)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ensure_registered(path, create_if_missing):
    """Make sure STEAM_LIB is registered in the given libraryfolders file.

    Returns one of: "created", "appended", "ok", "skipped", "refused".
    """
    if not os.path.isfile(path):
        if not create_if_missing:
            return "skipped"

        print("Creating Steam library registration for %s ..." % STEAM_LIB)
        # Two entries: the client's own install directory must always be in
        # the list, followed by the shared library.
        text = '"libraryfolders"\n{\n'
        text += make_entry(0, DEFAULT_LIB)
        text += make_entry(1, STEAM_LIB)
        text += "}\n"
        write_vdf(path, text)
        return "created"

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    if STEAM_LIB in registered_paths(text):
        return "ok"

    # Only touch files with the expected single-root structure: the root
    # object closes with a single column-0 '}' line at the end of the file.
    closing_lines = [line for line in text.splitlines() if line == "}"]
    if len(closing_lines) != 1 or not text.rstrip().endswith("}"):
        print(
            "Refusing to modify %s: unrecognized structure." % path,
            file=sys.stderr,
        )
        return "refused"

    indices = [int(m) for m in re.findall(r'\n\t"(\d+)"\n\t\{', text)]
    entry = make_entry(max(indices) + 1 if indices else 0, STEAM_LIB)
    root_close = text.rstrip().rfind("}")
    write_vdf(path, text[:root_close] + entry + text[root_close:])
    return "appended"


def main():
    if not os.path.isdir(STEAM_LIB):
        print("%s not found; skipping Steam library registration." % STEAM_LIB)
        return 0

    primary = ensure_registered(PRIMARY_PATH, create_if_missing=True)
    # The client loads the legacy copy first when it exists, so keep it in
    # sync too - but only ever append to it, never create it.
    legacy = ensure_registered(LEGACY_PATH, create_if_missing=False)

    if primary in ("created", "appended") or legacy == "appended":
        print("Steam library registered.")
    else:
        print("Steam library already registered; nothing to do.")
    return 0 if "refused" not in (primary, legacy) else 1


if __name__ == "__main__":
    sys.exit(main())
