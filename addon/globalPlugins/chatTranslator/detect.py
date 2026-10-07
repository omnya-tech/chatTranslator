# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Guesses, without any network request, whether a text is written in a given language.
# Used to let NVDA speak text in the user's own language straight away instead of
# sending everything to a translation service first. Nothing here imports NVDA.

import re

SCRIPTS = {
	"arabic": re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]"),
	"cyrillic": re.compile("[Ѐ-ӿ]"),
	"greek": re.compile("[Ͱ-Ͽ]"),
	"hebrew": re.compile("[֐-׿]"),
	"devanagari": re.compile("[ऀ-ॿ]"),
	"bengali": re.compile("[ঀ-৿]"),
	"thai": re.compile("[฀-๿]"),
	"hangul": re.compile("[가-힯ᄀ-ᇿ㄰-㆏]"),
	"kana": re.compile("[぀-ヿ]"),
	"han": re.compile("[一-鿿]"),
	"latin": re.compile("[A-Za-zÀ-ɏ]"),
}

# Scripts each language is written in; anything not listed is written in Latin letters.
LANGUAGE_SCRIPTS = {
	"ar": {"arabic"}, "fa": {"arabic"}, "ur": {"arabic"},
	"ru": {"cyrillic"}, "uk": {"cyrillic"},
	"el": {"greek"}, "he": {"hebrew"}, "hi": {"devanagari"}, "bn": {"bengali"}, "th": {"thai"},
	"ko": {"hangul", "han"}, "ja": {"kana", "han"}, "zh-CN": {"han"}, "zh-TW": {"han"},
}

# Frequent short words that tell Latin-script languages apart.
STOPWORDS = {
	"en": "the and you your is are was have has for with this that not will can our we to of in it be on at please thank thanks",
	"fr": "le la les des est et vous votre nous pour pas une dans que qui sur avec sont merci bonjour je",
	"de": "der die das und ist nicht sie ich wir ein eine mit für auf den dem ihre sind bitte danke",
	"es": "el los las del que y es en por para con una sus usted gracias hola su está pero",
	"it": "il gli della che di è e per una con non sono grazie ciao lei questo anche",
	"pt": "os as do da que e é em para com uma não você obrigado olá seu sua são",
	"nl": "de het een en is van dat niet je u wij met voor zijn op bedankt",
	"sv": "och att det är en jag inte för med som på tack ni vi har",
	"no": "og det er en jeg ikke for med som på takk dere vi har til",
	"da": "og det er en jeg ikke for med som på tak i vi har til",
	"fi": "ja on ei että se kiitos te me olen olet tämä mutta",
	"pl": "i nie jest to że na się w z do jak dziękuję pan pani",
	"cs": "a je to že na se v z do jak děkuji vy my není",
	"ro": "și este nu că pe cu la în pentru vă mulțumesc sunt",
	"hu": "és a az nem hogy van egy köszönöm ön mi is",
	"tr": "ve bir bu da de ne için ile çok teşekkür ederim siz biz",
	"id": "dan yang di ini itu untuk dengan tidak kami anda terima kasih",
	"ms": "dan yang di ini itu untuk dengan tidak kami anda terima kasih",
	"vi": "và là của có không cho với được tôi bạn cảm ơn",
	"sw": "na ya wa kwa ni la za katika asante wewe sisi",
}
STOPWORDS = {code: set(words.split()) for code, words in STOPWORDS.items()}
_WORD_RE = re.compile(r"[a-zà-ɏ']+")


def scriptsIn(text):
	"""Letter counts per script, ignoring scripts with no letters in the text."""
	counts = {}
	for name, pattern in SCRIPTS.items():
		found = len(pattern.findall(text))
		if found:
			counts[name] = found
	return counts


def isInLanguage(text, code):
	"""True when text looks written in language `code` (or has nothing to translate), False when it looks foreign."""
	counts = scriptsIn(text)
	if not counts:
		return True
	mine = LANGUAGE_SCRIPTS.get(code, {"latin"})
	ownLetters = sum(n for script, n in counts.items() if script in mine)
	if ownLetters * 2 < sum(counts.values()):
		return False
	if code == "zh-CN" or code == "zh-TW":
		# Japanese mixes Chinese characters with kana.
		return "kana" not in counts
	if mine != {"latin"}:
		return True
	words = _WORD_RE.findall(text.lower())
	scores = {lang: sum(word in stopwords for word in words) for lang, stopwords in STOPWORDS.items()}
	own = scores.get(code, 0)
	if max(scores.values()) > own:
		return False
	if own:
		return True
	# No clues either way: a few words are most likely an interface label in the user's language,
	# a longer text with none of the user's common words most likely is not.
	return len(words) < 4
