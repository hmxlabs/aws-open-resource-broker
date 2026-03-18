"""CLI argument contract tests — one file covering all 6 consistency fix tasks."""

import argparse

import pytest

from orb.cli.args import add_machine_actions, add_provider_actions, add_request_actions, add_template_actions
from orb.domain.machine.machine_status import MachineStatus


def _make_subparsers():
    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers(dest="action")
    sp._parser = parser  # stash parent for parse_args calls
    return sp


def _parse(sp, args):
    """Parse args using the parent parser that owns the subparsers."""
    return sp._parser.parse_args(args)


# ---------------------------------------------------------------------------
# Task 2046 — machines list --status enum choices
# ---------------------------------------------------------------------------


def test_machines_list_status_has_choices():
    sp = _make_subparsers()
    add_machine_actions(sp)
    list_parser = sp.choices["list"]
    status_action = next(a for a in list_parser._actions if "--status" in getattr(a, "option_strings", []))
    assert status_action.choices is not None and len(status_action.choices) > 0


def test_machines_list_status_choices_match_machine_status_enum():
    sp = _make_subparsers()
    add_machine_actions(sp)
    list_parser = sp.choices["list"]
    status_action = next(a for a in list_parser._actions if "--status" in getattr(a, "option_strings", []))
    assert set(status_action.choices) == {s.value for s in MachineStatus}


@pytest.mark.parametrize("valid_status", [s.value for s in MachineStatus])
def test_machines_list_valid_status_accepted(valid_status):
    sp = _make_subparsers()
    add_machine_actions(sp)
    ns = _parse(sp, ["list", "--status", valid_status])
    assert ns.status == valid_status


def test_machines_list_invalid_status_raises_argparse_error():
    sp = _make_subparsers()
    add_machine_actions(sp)
    with pytest.raises(SystemExit) as exc_info:
        _parse(sp, ["list", "--status", "not-a-real-status"])
    assert exc_info.value.code != 0
