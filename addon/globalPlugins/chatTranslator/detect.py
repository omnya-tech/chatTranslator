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
	"armenian": re.compile("[԰-֏]"),
	"georgian": re.compile("[Ⴀ-ჿ]"),
	"ethiopic": re.compile("[ሀ-፿]"),
	"devanagari": re.compile("[ऀ-ॿ]"),
	"bengali": re.compile("[ঀ-৿]"),
	"gurmukhi": re.compile("[਀-੿]"),
	"gujarati": re.compile("[઀-૿]"),
	"odia": re.compile("[଀-୿]"),
	"tamil": re.compile("[஀-௿]"),
	"telugu": re.compile("[ఀ-౿]"),
	"kannada": re.compile("[ಀ-೿]"),
	"malayalam": re.compile("[ഀ-ൿ]"),
	"sinhala": re.compile("[඀-෿]"),
	"thai": re.compile("[฀-๿]"),
	"lao": re.compile("[຀-໿]"),
	"myanmar": re.compile("[က-႟]"),
	"khmer": re.compile("[ក-៿]"),
	"hangul": re.compile("[가-힯ᄀ-ᇿ㄰-㆏]"),
	"kana": re.compile("[぀-ヿ]"),
	"han": re.compile("[一-鿿]"),
	"latin": re.compile("[A-Za-zÀ-ɏ]"),
}

# Scripts each language is written in; anything not listed is written in Latin letters.
LANGUAGE_SCRIPTS = {
	"ar": {"arabic"}, "fa": {"arabic"}, "ur": {"arabic"}, "ps": {"arabic"}, "sd": {"arabic"}, "ug": {"arabic"},
	"ru": {"cyrillic"}, "uk": {"cyrillic"}, "bg": {"cyrillic"}, "be": {"cyrillic"}, "mk": {"cyrillic"},
	"sr": {"cyrillic"}, "kk": {"cyrillic"}, "ky": {"cyrillic"}, "mn": {"cyrillic"}, "tg": {"cyrillic"},
	"tt": {"cyrillic"},
	"el": {"greek"}, "he": {"hebrew"}, "yi": {"hebrew"}, "hy": {"armenian"}, "ka": {"georgian"},
	"am": {"ethiopic"},
	"hi": {"devanagari"}, "mr": {"devanagari"}, "ne": {"devanagari"}, "bn": {"bengali"},
	"pa": {"gurmukhi"}, "gu": {"gujarati"}, "or": {"odia"}, "ta": {"tamil"}, "te": {"telugu"},
	"kn": {"kannada"}, "ml": {"malayalam"}, "si": {"sinhala"},
	"th": {"thai"}, "lo": {"lao"}, "my": {"myanmar"}, "km": {"khmer"},
	"ko": {"hangul", "han"}, "ja": {"kana", "han"}, "zh-CN": {"han"}, "zh-TW": {"han"},
}

# Letters that tell apart languages sharing a script.
# Arabic script: letters Arabic does not use, and letters only Urdu uses.
_PERSIAN_URDU_LETTERS = re.compile("[پچژگکی]")  # پ چ ژ گ ک ی
_URDU_LETTERS = re.compile("[ٹڈڑںےہھ]")  # ٹ ڈ ڑ ں ے ہ ھ
_ARABIC_LETTERS = re.compile("[ةيك]")  # ة ي ك
# Cyrillic: letters only Ukrainian uses, and letters only Russian uses.
_UKRAINIAN_LETTERS = re.compile("[іїєґІЇЄҐ]")  # і ї є ґ
_RUSSIAN_LETTERS = re.compile("[ыэъёЫЭЪЁ]")  # ы э ъ ё

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
	"ca": "el els les de que i és en per amb una no gràcies hola",
	"hr": "i je da se na u za su ne što kako hvala ovo ali",
	"bs": "i je da se na u za su ne šta kako hvala ovo ali",
	"sk": "a je to že na sa v z do ako ďakujem nie som pre",
	"sl": "in je da se na v za ne kako hvala ki so tudi",
	"lt": "ir yra kad į su ne tai ačiū kaip bet",
	"lv": "un ir ka uz ar nav tas paldies kā bet",
	"et": "ja on et ei see aitäh kuidas aga mis oli",
	"af": "die en is nie van het vir dit dankie ek jy",
	"sq": "dhe është që në për me një nuk faleminderit si",
	"az": "və bir bu üçün ilə da də nə çox təşəkkür deyil",
	"tl": "ang ng sa at ay mga na hindi ako ikaw salamat po",
	"uz": "va bir bu uchun bilan ham emas rahmat men siz",
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


# Frequent words of each Arabic-script language that the others do not use.
_ARABIC_WORDS = set("في على إلى هذا هذه أن لا هل التي الذي مع عن كان أنا أنت نحن هو هي ما لم لن قد".split())
_PERSIAN_WORDS = set("است این که را شما برای یک می خوب هستم نیست بود".split())
_URDU_WORDS = set("ہے کے میں کی اور کا سے کو آپ نہیں ہیں تھا یہ وہ پر بھی".split())
_ARABIC_SCRIPT_WORD_RE = re.compile("[؀-ۿ]+")


def arabicScriptLanguage(text):
	"""Arabic, Persian or Urdu by their telltale letters and words; None when the text gives no clue."""
	words = _ARABIC_SCRIPT_WORD_RE.findall(text)
	scores = {
		# The definite article starts a large share of Arabic words and almost none in the other two.
		"ar": len(_ARABIC_LETTERS.findall(text)) + sum(word.startswith("ال") and len(word) > 3 for word in words)
		+ 2 * sum(word in _ARABIC_WORDS for word in words),
		"fa": len(_PERSIAN_URDU_LETTERS.findall(text)) + 2 * sum(word in _PERSIAN_WORDS for word in words),
		# Urdu uses the Persian letters too, so its own letters weigh more.
		"ur": 2 * len(_URDU_LETTERS.findall(text)) + 2 * sum(word in _URDU_WORDS for word in words),
	}
	best = max(scores, key=scores.get)
	if scores[best] == 0 or list(scores.values()).count(scores[best]) > 1:
		return None
	return best


def cyrillicLanguage(text):
	"""Russian or Ukrainian by their telltale letters; None when the text gives no clue."""
	if _UKRAINIAN_LETTERS.search(text):
		return "uk"
	if _RUSSIAN_LETTERS.search(text):
		return "ru"
	return None


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
	if code in ("ar", "fa", "ur"):
		guess = arabicScriptLanguage(text)
		return guess is None or guess == code
	if code in ("ru", "uk"):
		guess = cyrillicLanguage(text)
		return guess is None or guess == code
	if mine != {"latin"}:
		return True
	words = _WORD_RE.findall(text.lower())
	scores = {lang: sum(word in stopwords for word in words) for lang, stopwords in STOPWORDS.items()}
	if code not in STOPWORDS:
		# Nothing is known about this language's words, so only clear evidence of another
		# language counts; otherwise everything the user reads would be sent for translation.
		return max(scores.values()) < 2
	own = scores.get(code, 0)
	if max(scores.values()) > own:
		return False
	if own:
		return True
	# No clues either way: a few words are most likely an interface label in the user's language,
	# a longer text with none of the user's common words most likely is not.
	return len(words) < 4


# Runs of letters, and everything between them.
_TOKEN_RE = re.compile(r"[^\W\d_]+|[\W\d_]+")
_LEADING_PUNCTUATION_RE = re.compile(r"[^\s\d]*")


def _wordKind(word, mine):
	"""Whether a word is in one of the user's scripts ("mine"), another known script ("foreign"), or neither."""
	for name, pattern in SCRIPTS.items():
		if pattern.match(word):
			return "mine" if name in mine else "foreign"
	return "neutral"


def splitForeign(text, code):
	"""Splits text into (piece, isForeign) so that only the foreign pieces need translating.

	Chat programs often read a message as one line: a few words in the user's language
	("Message from Ahmed:"), then the message itself, then the time. Sent whole, such a line is
	taken for the user's language by a translation service and comes back unchanged, so the part
	in another script is cut out and translated by itself. Where the two languages share a
	script the line cannot be cut, and is judged as a whole.
	"""
	whole = [(text, not isInLanguage(text, code))]
	mine = LANGUAGE_SCRIPTS.get(code, {"latin"})
	tokens = _TOKEN_RE.findall(text)
	kinds = [_wordKind(token, mine) if token[0].isalpha() else "neutral" for token in tokens]
	if "foreign" not in kinds or "mine" not in kinds:
		return whole

	# Group the tokens into alternating pieces; what lies between two words follows the rules below.
	pieces = []  # [kind, text, word count]
	pending = ""
	for token, kind in zip(tokens, kinds):
		if kind == "neutral":
			pending += token
			continue
		if pieces and pieces[-1][0] == kind:
			pieces[-1][1] += pending + token
			pieces[-1][2] += 1
		else:
			if pieces and pieces[-1][0] == "foreign":
				# Punctuation right after a foreign sentence stays with it; the rest starts the next piece.
				head = _LEADING_PUNCTUATION_RE.match(pending).group(0)
				pieces[-1][1] += head
				pending = pending[len(head):]
			elif pieces:
				pieces[-1][1] += pending
				pending = ""
			pieces.append([kind, pending + token, 1])
		pending = ""
	pieces[-1][1] += pending

	runs = [piece for piece in pieces if piece[0] == "foreign"]
	mostlyForeign = whole[0][1]
	if mostlyForeign and len(runs) > 1:
		# A foreign text with a few of the user's words inside it: cutting it up would wreck the sentences.
		return whole
	# A lone foreign word inside the user's own text is a name or a brand, not a message.
	result = [(piece[1], piece[0] == "foreign" and (mostlyForeign or piece[2] >= 2)) for piece in pieces]
	if not any(foreign for _piece, foreign in result):
		return [(text, False)]
	return result
