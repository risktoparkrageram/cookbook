import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from cookbook import db, schema

BACKUP_PREFIX = "recipes-"
BACKUP_SUFFIX = ".db"


def copy_database(source: Path, target: Path) -> None:
    """Copy a database with SQLite's online backup, consistent even while others write."""
    reader = sqlite3.connect(source)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()


def migrate_database(path: Path) -> tuple[int, int]:
    """
    Copy the database to PATH.bak, then apply pending migrations.

    Returns the schema version before and after. A path with no database is refused
    rather than created, so a typo can't start an empty cookbook.
    """
    if not path.is_file():
        raise FileNotFoundError(f"no database at {path}")
    copy_database(path, path.with_name(path.name + ".bak"))
    connection = db.connect(path)
    try:
        before = schema.current_version(connection)
        return before, schema.migrate(connection)
    finally:
        connection.close()


def back_up_database(path: Path, directory: Path, keep: int, now: datetime) -> Path:
    """
    Copy the database into directory as recipes-<UTC time>.db and keep only the newest.

    The copy is checked before it counts: it is written under a temporary name and
    renamed once SQLite's integrity check passes. The directory must already exist, so
    when the backup disk isn't mounted nothing is written to the disk underneath.
    Only files named like backups are ever removed.
    """
    if not path.is_file():
        raise FileNotFoundError(f"no database at {path}")
    if not directory.is_dir():
        raise FileNotFoundError(f"no backup directory at {directory}")
    target = directory / f"{BACKUP_PREFIX}{now.astimezone(UTC):%Y%m%dT%H%M%SZ}{BACKUP_SUFFIX}"
    partial = target.with_name(target.name + ".partial")
    copy_database(path, partial)
    check = sqlite3.connect(partial)
    try:
        (result,) = check.execute("PRAGMA integrity_check").fetchone()
    finally:
        check.close()
    if result != "ok":
        partial.unlink()
        raise RuntimeError(f"the backup failed SQLite's integrity check: {result}")
    partial.rename(target)
    backups = sorted(directory.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"), reverse=True)
    for old in backups[keep:]:
        old.unlink()
    return target


def main(arguments: list[str] | None = None) -> None:
    """Run cookbook migrate or cookbook backup; errors go to stderr with exit status 1."""
    parser = argparse.ArgumentParser(prog="cookbook")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("migrate", help="back up to DB.bak, then migrate the schema")
    migrate.add_argument("--db", type=Path, required=True)
    backup = commands.add_parser("backup", help="copy the database into a backup directory")
    backup.add_argument("--db", type=Path, required=True)
    backup.add_argument("--to", type=Path, required=True, dest="directory")
    backup.add_argument("--keep", type=int, default=30)
    options = parser.parse_args(arguments)

    try:
        if options.command == "migrate":
            before, after = migrate_database(options.db)
            print(f"{options.db}: schema version {before} -> {after}")
        else:
            if options.keep < 1:
                parser.error("--keep must be at least 1")
            target = back_up_database(
                options.db, options.directory, options.keep, datetime.now(UTC)
            )
            print(f"backed up to {target}")
    except (FileNotFoundError, RuntimeError) as error:
        print(f"cookbook: {error}", file=sys.stderr)
        sys.exit(1)
