# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# API keys live in Windows Credential Manager (generic credentials of the current user),
# not in nvda.ini where they would be plain text. Nothing here imports NVDA.

import ctypes
from ctypes import wintypes

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
TARGET_PREFIX = "NVDA chatTranslator: "


class _FILETIME(ctypes.Structure):
	_fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIAL(ctypes.Structure):
	_fields_ = [
		("Flags", wintypes.DWORD),
		("Type", wintypes.DWORD),
		("TargetName", wintypes.LPWSTR),
		("Comment", wintypes.LPWSTR),
		("LastWritten", _FILETIME),
		("CredentialBlobSize", wintypes.DWORD),
		("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
		("Persist", wintypes.DWORD),
		("AttributeCount", wintypes.DWORD),
		("Attributes", ctypes.c_void_p),
		("TargetAlias", wintypes.LPWSTR),
		("UserName", wintypes.LPWSTR),
	]


def _advapi():
	advapi = ctypes.WinDLL("advapi32", use_last_error=True)
	advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
	advapi.CredReadW.restype = wintypes.BOOL
	advapi.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wintypes.DWORD]
	advapi.CredWriteW.restype = wintypes.BOOL
	advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
	advapi.CredDeleteW.restype = wintypes.BOOL
	advapi.CredFree.argtypes = [ctypes.c_void_p]
	advapi.CredFree.restype = None
	return advapi


def read(name):
	"""The stored secret, or "" when there is none."""
	advapi = _advapi()
	pointer = ctypes.POINTER(_CREDENTIAL)()
	if not advapi.CredReadW(TARGET_PREFIX + name, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
		if ctypes.get_last_error() == ERROR_NOT_FOUND:
			return ""
		raise ctypes.WinError(ctypes.get_last_error())
	try:
		credential = pointer.contents
		blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
		return blob.decode("utf-16-le")
	finally:
		advapi.CredFree(pointer)


def write(name, secret):
	"""Stores the secret; an empty secret deletes it."""
	if not secret:
		delete(name)
		return
	advapi = _advapi()
	blob = secret.encode("utf-16-le")
	buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
	credential = _CREDENTIAL()
	credential.Type = CRED_TYPE_GENERIC
	credential.TargetName = TARGET_PREFIX + name
	credential.CredentialBlobSize = len(blob)
	credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
	credential.Persist = CRED_PERSIST_LOCAL_MACHINE
	credential.UserName = "chatTranslator"
	if not advapi.CredWriteW(ctypes.byref(credential), 0):
		raise ctypes.WinError(ctypes.get_last_error())


def delete(name):
	advapi = _advapi()
	if not advapi.CredDeleteW(TARGET_PREFIX + name, CRED_TYPE_GENERIC, 0):
		if ctypes.get_last_error() != ERROR_NOT_FOUND:
			raise ctypes.WinError(ctypes.get_last_error())
