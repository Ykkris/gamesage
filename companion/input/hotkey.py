"""Platform-neutral hotkey model, parsing, and validation.

A hotkey is a key plus optional modifiers, written as ``"ctrl+f8"``.
This module holds no OS integration; the Windows listener lives in
:mod:`companion.input.win32_hotkey`.
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWN_MODIFIERS = frozenset({"ctrl", "alt", "shift", "win"})

#: Display and parse order for modifiers.
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")


class HotkeyError(Exception):
    """Base class for hotkey configuration and registration failures."""


class InvalidHotkeyError(HotkeyError, ValueError):
    """A hotkey string could not be parsed."""


class HotkeyRegistrationError(HotkeyError):
    """The OS refused to register the hotkey."""


@dataclass(frozen=True)
class Hotkey:
    key: str
    modifiers: frozenset[str]

    @classmethod
    def parse(cls, text: str) -> "Hotkey":
        """Parse a hotkey like ``"ctrl+alt+f8"``.

        Raises:
            InvalidHotkeyError: malformed text, unknown or duplicated
                modifiers, or a missing non-modifier key.
        """
        tokens = [token.strip().lower() for token in text.split("+")]
        if not tokens or any(not token for token in tokens):
            raise InvalidHotkeyError(f"Invalid hotkey {text!r}: empty part.")
        *modifier_tokens, key = tokens
        if key in KNOWN_MODIFIERS:
            raise InvalidHotkeyError(
                f"Invalid hotkey {text!r}: must end with a non-modifier key."
            )
        modifiers: set[str] = set()
        for token in modifier_tokens:
            if token not in KNOWN_MODIFIERS:
                raise InvalidHotkeyError(
                    f"Invalid hotkey {text!r}: unknown modifier {token!r}."
                )
            if token in modifiers:
                raise InvalidHotkeyError(
                    f"Invalid hotkey {text!r}: duplicate modifier {token!r}."
                )
            modifiers.add(token)
        return cls(key=key, modifiers=frozenset(modifiers))

    def __str__(self) -> str:
        parts = [
            modifier for modifier in _MODIFIER_ORDER if modifier in self.modifiers
        ]
        parts.append(self.key)
        return "+".join(parts).title()


def virtual_key_code(key: str) -> int | None:
    """Map a key name to its Win32 virtual-key code, or None if unknown.

    Supports single letters, single digits, and F1 through F24.
    """
    key = key.lower()
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return ord(key)
    if len(key) in (2, 3) and key.startswith("f") and key[1:].isdigit():
        function_key = int(key[1:])
        if 1 <= function_key <= 24:
            return 0x70 + function_key - 1
    return None
