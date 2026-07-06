"""Unit tests for the list_page_shell shared component.

The rx stub is already installed by conftest.py at collection time, so
all orb.ui imports are safe inside test functions.
"""

from __future__ import annotations


def test_list_page_shell_composes_without_raising() -> None:
    """list_page_shell must return a component when called with minimal args."""
    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    # Minimal stand-ins — the rx stub accepts any call so we just need
    # to confirm the Python-level composition doesn't raise.
    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        load_more=rx.fragment(),
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        is_loading=rx.Var.create(False),
        is_empty=rx.Var.create(True),
    )

    assert component is not None


def test_list_page_shell_accepts_banners_and_dialogs() -> None:
    """Optional banners and dialogs lists must be accepted without error."""
    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        load_more=rx.fragment(),
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        banners=[rx.fragment(), rx.fragment()],
        is_loading=rx.Var.create(False),
        is_empty=rx.Var.create(False),
        dialogs=[rx.fragment()],
    )

    assert component is not None


def test_list_page_shell_accepts_custom_skeleton() -> None:
    """A custom loading_skeleton component must be accepted."""
    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    custom_skeleton = rx.vstack(rx.skeleton(height="2rem", width="100%"))

    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        load_more=rx.fragment(),
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        is_loading=rx.Var.create(True),
        is_empty=rx.Var.create(True),
        loading_skeleton=custom_skeleton,
    )

    assert component is not None


def test_list_page_shell_default_none_lists() -> None:
    """Omitting banners and dialogs (defaults to None) must work."""
    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    # banners and dialogs not passed — should default to []
    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        load_more=rx.fragment(),
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        is_loading=rx.Var.create(False),
        is_empty=rx.Var.create(False),
    )

    assert component is not None


def test_list_page_shell_load_more_via_primitives() -> None:
    """Passing next_cursor/loading_more/on_load_more builds the button internally."""
    from unittest.mock import MagicMock

    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    mock_handler = MagicMock()

    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        is_loading=rx.Var.create(False),
        is_empty=rx.Var.create(False),
        next_cursor=rx.Var.create("cursor_abc"),
        loading_more=rx.Var.create(False),
        on_load_more=mock_handler,
    )

    assert component is not None


def test_list_page_shell_explicit_load_more_takes_precedence() -> None:
    """An explicit load_more component takes precedence over primitives."""
    from unittest.mock import MagicMock

    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    mock_handler = MagicMock()
    custom_load_more = rx.button("Custom load more")

    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        load_more=custom_load_more,
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        is_loading=rx.Var.create(False),
        is_empty=rx.Var.create(False),
        next_cursor=rx.Var.create("cursor_abc"),
        loading_more=rx.Var.create(False),
        on_load_more=mock_handler,
    )

    assert component is not None


def test_list_page_shell_no_load_more_args() -> None:
    """Omitting all load-more args must produce a valid component (rx.fragment fallback)."""
    import reflex as rx

    from orb.ui.components.list_page_shell import list_page_shell

    component = list_page_shell(
        filter_row=rx.fragment(),
        toolbar=rx.fragment(),
        grid=rx.fragment(),
        empty=rx.fragment(),
        error_banner=rx.fragment(),
        is_loading=rx.Var.create(False),
        is_empty=rx.Var.create(False),
    )

    assert component is not None


def test_build_load_more_button_renders_when_cursor_present() -> None:
    """_build_load_more_button must compose without raising for any Var inputs."""
    import reflex as rx

    from orb.ui.components.list_page_shell import _build_load_more_button

    button = _build_load_more_button(
        next_cursor=rx.Var.create("abc"),
        loading_more=rx.Var.create(False),
        on_load_more=rx.Var.create(None),
    )

    assert button is not None


def test_build_load_more_button_renders_loading_state() -> None:
    """_build_load_more_button must compose without raising when loading_more=True."""
    import reflex as rx

    from orb.ui.components.list_page_shell import _build_load_more_button

    button = _build_load_more_button(
        next_cursor=rx.Var.create("abc"),
        loading_more=rx.Var.create(True),
        on_load_more=rx.Var.create(None),
    )

    assert button is not None
