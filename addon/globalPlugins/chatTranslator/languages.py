# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Languages offered for translation: (code, English name).
# Codes are the ones Google Translate uses. The English name is what Claude is told;
# the user sees it translated into NVDA's language.
# The most widely used languages come first, then the rest in alphabetical order.

try:
	import addonHandler
	addonHandler.initTranslation()
except ImportError:
	def _(text):
		return text

LANGUAGES = (
	("en", "English"),
	("ar", "Arabic"),
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
	("af", "Afrikaans"),
	("sq", "Albanian"),
	("am", "Amharic"),
	("hy", "Armenian"),
	("az", "Azerbaijani"),
	("eu", "Basque"),
	("be", "Belarusian"),
	("bs", "Bosnian"),
	("bg", "Bulgarian"),
	("my", "Burmese"),
	("ca", "Catalan"),
	("ceb", "Cebuano"),
	("ny", "Chichewa"),
	("co", "Corsican"),
	("hr", "Croatian"),
	("cs", "Czech"),
	("da", "Danish"),
	("nl", "Dutch"),
	("eo", "Esperanto"),
	("et", "Estonian"),
	("tl", "Filipino"),
	("fi", "Finnish"),
	("fy", "Frisian"),
	("gl", "Galician"),
	("ka", "Georgian"),
	("el", "Greek"),
	("gu", "Gujarati"),
	("ht", "Haitian Creole"),
	("ha", "Hausa"),
	("haw", "Hawaiian"),
	("he", "Hebrew"),
	("hmn", "Hmong"),
	("hu", "Hungarian"),
	("is", "Icelandic"),
	("ig", "Igbo"),
	("ga", "Irish"),
	("jw", "Javanese"),
	("kn", "Kannada"),
	("kk", "Kazakh"),
	("km", "Khmer"),
	("rw", "Kinyarwanda"),
	("ku", "Kurdish"),
	("ky", "Kyrgyz"),
	("lo", "Lao"),
	("la", "Latin"),
	("lv", "Latvian"),
	("lt", "Lithuanian"),
	("lb", "Luxembourgish"),
	("mk", "Macedonian"),
	("mg", "Malagasy"),
	("ml", "Malayalam"),
	("mt", "Maltese"),
	("mi", "Maori"),
	("mr", "Marathi"),
	("mn", "Mongolian"),
	("ne", "Nepali"),
	("no", "Norwegian"),
	("or", "Odia"),
	("ps", "Pashto"),
	("pl", "Polish"),
	("pa", "Punjabi"),
	("ro", "Romanian"),
	("sm", "Samoan"),
	("gd", "Scottish Gaelic"),
	("sr", "Serbian"),
	("st", "Sesotho"),
	("sn", "Shona"),
	("sd", "Sindhi"),
	("si", "Sinhala"),
	("sk", "Slovak"),
	("sl", "Slovenian"),
	("so", "Somali"),
	("su", "Sundanese"),
	("sw", "Swahili"),
	("sv", "Swedish"),
	("tg", "Tajik"),
	("ta", "Tamil"),
	("tt", "Tatar"),
	("te", "Telugu"),
	("th", "Thai"),
	("tk", "Turkmen"),
	("uk", "Ukrainian"),
	("ug", "Uyghur"),
	("uz", "Uzbek"),
	("vi", "Vietnamese"),
	("cy", "Welsh"),
	("xh", "Xhosa"),
	("yi", "Yiddish"),
	("yo", "Yoruba"),
	("zu", "Zulu"),
)

_BY_CODE = dict(LANGUAGES)

# NVDA's speech uses underscores where our codes use hyphens.
_SPEECH_CODES = {"zh-CN": "zh_CN", "zh-TW": "zh_TW", "jw": "jv"}


def englishName(code):
	return _BY_CODE.get(code, code)


def displayName(code):
	"""The language name in NVDA's interface language."""
	return _(englishName(code))


def speechCode(code):
	"""The code NVDA's speech expects for switching the voice to this language."""
	return _SPEECH_CODES.get(code, code)


def codes():
	return [code for code, _name in LANGUAGES]


def displayNames():
	return [_(name) for _code, name in LANGUAGES]
