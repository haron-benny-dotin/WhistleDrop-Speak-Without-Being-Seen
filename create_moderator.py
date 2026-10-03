# usage: python create_moderator.py <username>

import argparse
import getpass
import sqlite3
import sys

from whistledrop import store
from whistledrop.config import load_settings
from whistledrop.db import connect, init_db

MIN_PASSWORD_LENGTH = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a WhistleDrop moderator.")
    parser.add_argument("username")
    parser.add_argument("--password", help="Omit to be prompted (recommended).")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        return 1

    settings = load_settings()
    init_db(settings.database_path)
    conn = connect(settings.database_path)
    try:
        store.create_moderator(conn, args.username, password)
    except sqlite3.IntegrityError:
        print(f"A moderator named '{args.username}' already exists.")
        return 1
    finally:
        conn.close()

    print(f"Moderator '{args.username}' created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
