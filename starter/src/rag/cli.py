from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .settings import Command, Settings, SettingsConfigurationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="ingest a Markdown directory")
    ingest.add_argument("directory", type=Path)
    ingest.set_defaults(command=Command.INGEST)

    bot = commands.add_parser("bot", help="run the Telegram bot")
    bot.set_defaults(command=Command.BOT)

    smoke = commands.add_parser("smoke", help="run an opt-in smoke check")
    smoke.add_argument("--artifact", type=Path, required=True)
    smoke.add_argument("--question", required=True)
    smoke.add_argument("--collection", required=True)
    smoke.set_defaults(command=Command.SMOKE)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        Settings().validate_for(args.command, collection=getattr(args, "collection", None))
    except ValidationError as error:
        invalid = [
            "RAG_" + "_".join(str(part).upper() for part in issue["loc"])
            for issue in error.errors()
        ]
        parser.error(str(SettingsConfigurationError(args.command, [], invalid)))
    except SettingsConfigurationError as error:
        parser.error(str(error))

    print(f"rag {args.command.value} is not available in the bootstrap package.", file=sys.stderr)
    return 2
