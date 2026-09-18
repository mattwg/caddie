"""Caddie's command-line entry point (`caddie <subcommand>`)."""

import argparse

from caddie.install.command import add_subparser as add_install_subparser
from caddie.list.command import add_subparser as add_list_subparser
from caddie.notebook.command import add_subparser as add_notebook_build_subparser
from caddie.notebook.rerun import add_subparser as add_notebook_rerun_subparser
from caddie.update.command import add_subparser as add_update_subparser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="caddie")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_install_subparser(subparsers)
    add_update_subparser(subparsers)
    add_notebook_build_subparser(subparsers)
    add_notebook_rerun_subparser(subparsers)
    add_list_subparser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.handler(args))
