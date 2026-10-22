# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Run by NVDA when the add-on is installed or removed.

import os
import sys


def onUninstall():
	"""API keys are secrets: do not leave them in Windows Credential Manager after the add-on is gone."""
	folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "globalPlugins", "chatTranslator")
	sys.path.insert(0, folder)
	try:
		import credentials
		for name in ("claude", "deepl"):
			try:
				credentials.delete(name)
			except OSError:
				pass
	except Exception:
		pass
	finally:
		sys.path.remove(folder)
