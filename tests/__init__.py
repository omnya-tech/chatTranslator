# Loads the add-on's NVDA-free modules (translators, languages) without NVDA.
# The package's own __init__.py needs NVDA, so a bare package object stands in for it.

import os
import sys
import types

PACKAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "addon", "globalPlugins", "chatTranslator")

if "chatTranslatorTest" not in sys.modules:
	package = types.ModuleType("chatTranslatorTest")
	package.__path__ = [PACKAGE_DIR]
	sys.modules["chatTranslatorTest"] = package
