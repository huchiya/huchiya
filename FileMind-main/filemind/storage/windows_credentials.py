"""Minimal Windows Credential Manager wrapper using only the standard library."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _Credential(ctypes.Structure):
    _fields_ = [
        ("flags", wintypes.DWORD), ("credential_type", wintypes.DWORD),
        ("target_name", wintypes.LPWSTR), ("comment", wintypes.LPWSTR),
        ("last_written", _FileTime), ("credential_blob_size", wintypes.DWORD),
        ("credential_blob", ctypes.POINTER(ctypes.c_byte)), ("persist", wintypes.DWORD),
        ("attribute_count", wintypes.DWORD), ("attributes", ctypes.c_void_p),
        ("target_alias", wintypes.LPWSTR), ("user_name", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """Persist API keys for the current Windows user in Credential Manager."""

    def __init__(self) -> None:
        if not hasattr(ctypes, "WinDLL"):
            raise OSError("Windows Credential Manager is unavailable")
        self._api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                        ctypes.POINTER(ctypes.POINTER(_Credential))]
        self._api.CredReadW.restype = wintypes.BOOL
        self._api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
        self._api.CredWriteW.restype = wintypes.BOOL
        self._api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._api.CredDeleteW.restype = wintypes.BOOL
        self._api.CredFree.argtypes = [ctypes.c_void_p]
        self._api.CredFree.restype = None

    def get(self, target: str) -> str | None:
        pointer = ctypes.POINTER(_Credential)()
        if not self._api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            error_code = ctypes.get_last_error()
            if error_code == ERROR_NOT_FOUND:
                return None
            raise OSError(error_code, "Windows Credential Manager read failed")
        try:
            credential = pointer.contents
            return ctypes.string_at(credential.credential_blob, credential.credential_blob_size).decode("utf-8")
        finally:
            self._api.CredFree(pointer)

    def set(self, target: str, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > 2560:
            raise ValueError("API Key 超过 Windows 凭据存储长度限制")
        blob = (ctypes.c_byte * len(encoded)).from_buffer_copy(encoded)
        credential = _Credential(
            0, CRED_TYPE_GENERIC, target, "FileMind AI provider key", _FileTime(),
            len(encoded), ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte)),
            CRED_PERSIST_LOCAL_MACHINE, 0, None, None, "FileMind",
        )
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "Windows Credential Manager write failed")

    def delete(self, target: str) -> None:
        if not self._api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
            error_code = ctypes.get_last_error()
            if error_code != ERROR_NOT_FOUND:
                raise OSError(error_code, "Windows Credential Manager delete failed")
