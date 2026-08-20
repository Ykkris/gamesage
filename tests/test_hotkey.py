"""Tests for the platform-neutral hotkey model and parsing."""

import pytest

from companion.input.hotkey import Hotkey, InvalidHotkeyError, virtual_key_code


class TestHotkeyParse:
    def test_parses_modifier_and_key(self):
        hotkey = Hotkey.parse("ctrl+f8")
        assert hotkey.key == "f8"
        assert hotkey.modifiers == frozenset({"ctrl"})

    def test_parse_is_case_and_space_insensitive(self):
        assert Hotkey.parse("  CTRL + F8 ") == Hotkey(
            key="f8", modifiers=frozenset({"ctrl"})
        )

    def test_parses_bare_key(self):
        assert Hotkey.parse("f8") == Hotkey(key="f8", modifiers=frozenset())

    def test_parses_multiple_modifiers(self):
        hotkey = Hotkey.parse("ctrl+alt+shift+f8")
        assert hotkey.modifiers == frozenset({"ctrl", "alt", "shift"})

    def test_rejects_unknown_modifier(self):
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("hup+f8")

    def test_rejects_duplicate_modifier(self):
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("ctrl+ctrl+f8")

    def test_rejects_modifier_without_key(self):
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("ctrl+")

    def test_rejects_empty_string(self):
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("")

    def test_rejects_multiple_keys(self):
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("ctrl+f8+q")

    def test_rejects_modifier_as_key(self):
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("ctrl+alt")
        with pytest.raises(InvalidHotkeyError):
            Hotkey.parse("alt")


class TestHotkeyStr:
    def test_formats_in_canonical_modifier_order(self):
        assert str(Hotkey.parse("shift+alt+ctrl+f8")) == "Ctrl+Alt+Shift+F8"

    def test_formats_bare_key(self):
        assert str(Hotkey.parse("f8")) == "F8"


class TestVirtualKeyCode:
    def test_function_keys(self):
        assert virtual_key_code("f1") == 0x70
        assert virtual_key_code("f8") == 0x77
        assert virtual_key_code("f24") == 0x87

    def test_letters_and_digits(self):
        assert virtual_key_code("a") == 0x41
        assert virtual_key_code("5") == 0x35

    def test_unknown_key_returns_none(self):
        assert virtual_key_code("f25") is None
        assert virtual_key_code("foo") is None
