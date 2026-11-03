"""Usage: python -m app.cli create-admin --email E --name N"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import func, select

from app.auth.security import hash_password
from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.models import Role, User


async def create_admin(email: str, name: str, password: str) -> None:
    engine = make_engine(get_settings().database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            email = email.strip().lower()
            if (await db.execute(select(User.id).where(func.lower(User.email) == email))).first():
                sys.exit(f"já existe usuário com email {email}")
            db.add(User(email=email, name=name, role=Role.ADMIN, password_hash=hash_password(password)))
            await db.commit()
    finally:
        await engine.dispose()
    print(f"admin {email} criado")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    args = parser.parse_args()
    pw = getpass.getpass("Senha (mín. 8): ")
    if len(pw) < 8 or pw != getpass.getpass("Repita: "):
        sys.exit("senha curta ou não confere")
    asyncio.run(create_admin(args.email, args.name, pw))


if __name__ == "__main__":
    main()
