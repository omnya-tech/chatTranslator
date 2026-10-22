# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Puts text on the clipboard without it being kept in Windows' clipboard history (Windows+V)
# or synced to the user's other devices. The add-on passes translations of private messages
# through the clipboard for a moment; they have no business staying there.
# Nothing here imports NVDA.

import ctypes
import struct
import time
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Formats Windows looks for; see "Clipboard Formats" in the Windows documentation.
_PRIVACY_FORMATS = (
	"ExcludeClipboardContentFromMonitorProcessing",
	"CanIncludeInClipboardHistory",
	"CanUploadToCloudClipboard",
)


def _libraries():
	user32 = ctypes.WinDLL("user32", use_last_error=True)
	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	user32.OpenClipboard.argtypes = [wintypes.HWND]
	user32.OpenClipboard.restype = wintypes.BOOL
	user32.EmptyClipboard.restype = wintypes.BOOL
	user32.CloseClipboard.restype = wintypes.BOOL
	user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
	user32.SetClipboardData.restype = wintypes.HANDLE
	user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
	user32.RegisterClipboardFormatW.restype = wintypes.UINT
	kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
	kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
	kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
	kernel32.GlobalLock.restype = ctypes.c_void_p
	kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
	kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
	return user32, kernel32


def _put(user32, kernel32, clipboardFormat, data):
	handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
	if not handle:
		raise ctypes.WinError(ctypes.get_last_error())
	pointer = kernel32.GlobalLock(handle)
	if not pointer:
		kernel32.GlobalFree(handle)
		raise ctypes.WinError(ctypes.get_last_error())
	ctypes.memmove(pointer, data, len(data))
	kernel32.GlobalUnlock(handle)
	if not user32.SetClipboardData(clipboardFormat, handle):
		# The clipboard owns the memory only once it has accepted it.
		error = ctypes.get_last_error()
		kernel32.GlobalFree(handle)
		raise ctypes.WinError(error)


def copyPrivately(text, window=None):
	"""Replaces the clipboard with text, marked to stay out of the clipboard history and cloud sync."""
	user32, kernel32 = _libraries()
	# Another program may hold the clipboard for an instant.
	for attempt in range(10):
		if user32.OpenClipboard(window):
			break
		time.sleep(0.02)
	else:
		raise ctypes.WinError(ctypes.get_last_error())
	try:
		user32.EmptyClipboard()
		_put(user32, kernel32, CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
		for name in _PRIVACY_FORMATS:
			_put(user32, kernel32, user32.RegisterClipboardFormatW(name), struct.pack("I", 0))
	finally:
		user32.CloseClipboard()
