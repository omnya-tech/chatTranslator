# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Languages offered for translation: (code, English name).
# Codes are the ones Google Translate uses. The English name is what Claude is told;
# the user sees it translated into NVDA's language.

try:
	import addonHandler
	addonHandler.initTranslation()
except ImportError:
	def _(text):
		return text

LANGUAGES = (
	("en", "English"),
	("fr", "French"),
	("de", "German"),
	("es", "Spanish"),
	("it", "Italian"),
	("pt", "Portuguese"),
	("ru", "Russian"),
	("tr", "Turkish"),
	("fa", "Persian"),
	("ur", "Urdu"),
	("hi", "Hindi"),
	("bn", "Bengali"),
	("zh-CN", "Simplified Chinese"),
	("zh-TW", "Traditional Chinese"),
	("ja", "Japanese"),
	("ko", "Korean"),
	("id", "Indonesian"),
	("ms", "Malay"),
	("th", "Thai"),
	("vi", "Vietnamese"),
	("nl", "Dutch"),
	("sv", "Swedish"),
	("no", "Norwegian"),
	("da", "Danish"),
	("fi", "Finnish"),
	("pl", "Polish"),
	("cs", "Czech"),
	("el", "Greek"),
	("ro", "Romanian"),
	("hu", "Hungarian"),
	("uk", "Ukrainian"),
	("he", "Hebrew"),
	("sw", "Swahili"),
	("ar", "Arabic"),
)

_BY_CODE = dict(LANGUAGES)


def englishName(code):
	return _BY_CODE.get(code, code)


def displayName(code):
	"""The language name in NVDA's interface language."""
	return _(englishName(code))


def codes():
	return [code for code, _name in LANGUAGES]


def displayNames():
	return [_(name) for _code, name in LANGUAGES]
