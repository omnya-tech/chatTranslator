# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Translation engines. NVDA is only needed for translated messages, so this can be tested on its own.

import http.cookiejar
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import languages

try:
	import addonHandler
	addonHandler.initTranslation()
except ImportError:
	def _(text):
		return text

USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# (key, label). The free ones, which need no key, are tried in this order when falling back.
ENGINES = (
	("google", _("Google Translate (free)")),
	("bing", _("Microsoft Bing Translator (free)")),
	("mymemory", _("MyMemory (free, with a daily limit)")),
	("deepl", _("DeepL (excellent, requires a free API key)")),
	("claude", _("Claude (most accurate, requires an API key)")),
)
FREE_ENGINES = ("google", "bing", "mymemory")
# Services that need an API key, stored in Windows Credential Manager under these names.
KEYED_ENGINES = ("deepl", "claude")
ENGINE_NAMES = {
	"google": _("Google"),
	"bing": _("Microsoft Bing"),
	"mymemory": "MyMemory",
	"deepl": "DeepL",
	"claude": "Claude",
}


class TranslationError(Exception):
	pass


def _open(request, timeout, service, opener=None):
	try:
		with (opener.open if opener else urllib.request.urlopen)(request, timeout=timeout) as response:
			return response.read().decode("utf-8")
	except urllib.error.HTTPError as e:
		raise TranslationError(_("%(service)s returned error %(code)d") % {"service": service, "code": e.code})
	except Exception as e:
		raise TranslationError(_("Could not connect to %(service)s: %(error)s") % {"service": service, "error": e})


def _chunks(text, limit):
	"""Splits text into pieces of at most limit characters, preferring line and sentence ends."""
	pieces = []
	while len(text) > limit:
		cut = max(text.rfind(sep, 0, limit) for sep in ("\n", ". ", "؟", "?", "!", "، ", ", ", " "))
		cut = cut + 1 if cut > 0 else limit
		pieces.append(text[:cut])
		text = text[cut:]
	if text:
		pieces.append(text)
	return pieces


def _byChunks(text, limit, translateChunk):
	parts = []
	for piece in _chunks(text, limit):
		stripped = piece.strip()
		if not stripped:
			parts.append(piece)
			continue
		lead = piece[:len(piece) - len(piece.lstrip())]
		trail = piece[len(piece.rstrip()):]
		parts.append(lead + translateChunk(stripped) + trail)
	return "".join(parts)


def _normalizeDetected(code):
	"""Maps a service's language code to ours (zh-Hans -> zh-CN, en-GB -> en)."""
	if not code or not isinstance(code, str):
		return None
	code = {"zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "nb": "no", "iw": "he"}.get(code, code)
	if code in ("zh-CN", "zh-TW"):
		return code
	code = code.split("-")[0].lower()
	return {"zh": "zh-CN", "nb": "no", "iw": "he"}.get(code, code)


# Google

def google(text, target, source="auto", timeout=10):
	data = urllib.parse.urlencode({
		"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text,
	}).encode("utf-8")
	request = urllib.request.Request(
		"https://translate.googleapis.com/translate_a/single", data=data,
		headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
	)
	try:
		result = json.loads(_open(request, timeout, ENGINE_NAMES["google"]))
		translated = "".join(segment[0] for segment in result[0] if segment and segment[0])
		detected = result[2] if len(result) > 2 else None
	except TranslationError:
		raise
	except Exception:
		raise TranslationError(_("Could not understand the response from %s") % ENGINE_NAMES["google"])
	if not translated:
		raise TranslationError(_("%s returned an empty translation") % ENGINE_NAMES["google"])
	return translated, _normalizeDetected(detected)


# Microsoft Bing: the free web translator needs tokens scraped from its page.

_BING_CODES = {"zh-CN": "zh-Hans", "zh-TW": "zh-Hant", "no": "nb"}
_BING_LIMIT = 1000
_BING_SESSION_SECONDS = 600
_bingLock = threading.Lock()
_bingSession = None


def _bingNewSession(timeout):
	jar = http.cookiejar.CookieJar()
	opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
	request = urllib.request.Request("https://www.bing.com/translator", headers={"User-Agent": USER_AGENT})
	try:
		with opener.open(request, timeout=timeout) as response:
			page = response.read().decode("utf-8")
			host = urllib.parse.urlparse(response.geturl()).netloc
	except Exception as e:
		raise TranslationError(_("Could not connect to %(service)s: %(error)s") % {"service": ENGINE_NAMES["bing"], "error": e})
	try:
		ig = re.search(r'IG:"([^"]+)"', page).group(1)
		iid = re.search(r'data-iid="([^"]+)"', page).group(1)
		key, token = json.loads(re.search(r"params_AbusePreventionHelper\s*=\s*(\[[^\]]+\])", page).group(1))[:2]
	except Exception:
		raise TranslationError(_("The Microsoft Bing page has changed and can no longer be used"))
	return {
		"opener": opener, "host": host, "ig": ig, "iid": iid,
		"key": key, "token": token, "created": time.monotonic(),
	}


def _bingGetSession(timeout, fresh=False):
	global _bingSession
	with _bingLock:
		if fresh or not _bingSession or time.monotonic() - _bingSession["created"] > _BING_SESSION_SECONDS:
			_bingSession = _bingNewSession(timeout)
		return _bingSession


def bing(text, target, timeout=10):
	to = _BING_CODES.get(target, target)
	detected = []

	def translateChunk(chunk, retry=True):
		session = _bingGetSession(timeout, fresh=not retry)
		data = urllib.parse.urlencode({
			"fromLang": "auto-detect", "to": to, "text": chunk,
			"token": session["token"], "key": session["key"],
		}).encode("utf-8")
		url = "https://%s/ttranslatev3?isVertical=1&IG=%s&IID=%s.1" % (session["host"], session["ig"], session["iid"])
		request = urllib.request.Request(url, data=data, headers={
			"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded",
		})
		try:
			result = json.loads(_open(request, timeout, ENGINE_NAMES["bing"], session["opener"]))
			detected.append(result[0].get("detectedLanguage", {}).get("language"))
			return result[0]["translations"][0]["text"]
		except Exception:
			if retry:
				# The tokens may have expired; get new ones once.
				return translateChunk(chunk, retry=False)
			raise TranslationError(_("Could not understand the response from %s") % ENGINE_NAMES["bing"])

	translated = _byChunks(text, _BING_LIMIT, translateChunk)
	return translated, _normalizeDetected(detected[0] if detected else None)


# MyMemory: free without a key, up to 500 characters per request and a daily quota.

_MYMEMORY_LIMIT = 450


def mymemory(text, target, source="auto", timeout=15):
	pair = "%s|%s" % ("Autodetect" if source == "auto" else source, target)
	detected = []

	def translateChunk(chunk):
		url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({"q": chunk, "langpair": pair})
		request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
		try:
			result = json.loads(_open(request, timeout, ENGINE_NAMES["mymemory"]))
		except TranslationError:
			raise
		except Exception:
			raise TranslationError(_("Could not understand the response from %s") % ENGINE_NAMES["mymemory"])
		if result.get("quotaFinished"):
			raise TranslationError(_("The free daily limit of MyMemory has been used up"))
		if str(result.get("responseStatus")) != "200":
			raise TranslationError(_("%(service)s returned an error: %(error)s") % {
				"service": ENGINE_NAMES["mymemory"], "error": result.get("responseDetails", ""),
			})
		detected.append(result["responseData"].get("detectedLanguage"))
		return result["responseData"]["translatedText"]

	translated = _byChunks(text, _MYMEMORY_LIMIT, translateChunk)
	if source != "auto":
		return translated, source
	return translated, _normalizeDetected(detected[0] if detected else None)


# Claude

def _claudeSystemPrompt(target, purpose, formal):
	lang = languages.englishName(target)
	lines = [
		"You are a translation engine inside a screen reader add-on.",
		"Translate the user's text into %s." % lang,
		"Start your reply with the source language's ISO 639-1 code in square brackets, such as [fr], then a space.",
		"Apart from that tag, output only the translation: no quotes, notes, explanations or alternatives.",
		"Keep names, numbers, links, emoji and line breaks as they are.",
		"Copy placeholder tokens such as %s0 exactly as they are." % PLACEHOLDER,
		"If the text is already in %s, output it unchanged." % lang,
	]
	if purpose == "outgoing":
		lines.append("The text is a chat message the user is sending to a foreign company or organisation.")
		if formal:
			lines.append("Use a polite, clear, professional tone suitable for business correspondence.")
		else:
			lines.append("Keep the tone of the original.")
	elif purpose == "check":
		lines.append(
			"The text is the user's own message after machine translation; "
			"translate it back faithfully so the user can check its meaning."
		)
	else:
		lines.append("The text is something a screen reader is about to speak; translate it faithfully and naturally.")
	return "\n".join(lines)


def claude(text, target, apiKey, model=CLAUDE_DEFAULT_MODEL, purpose="incoming", formal=True, timeout=30):
	if not apiKey:
		raise TranslationError(_("No Claude API key has been entered; enter it in the add-on settings"))
	body = json.dumps({
		"model": model or CLAUDE_DEFAULT_MODEL,
		"max_tokens": 4096,
		"system": _claudeSystemPrompt(target, purpose, formal),
		"messages": [{"role": "user", "content": text}],
	}).encode("utf-8")
	request = urllib.request.Request(CLAUDE_URL, data=body, headers={
		"x-api-key": apiKey,
		"anthropic-version": "2023-06-01",
		"content-type": "application/json",
	})
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			result = json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as e:
		try:
			message = json.loads(e.read().decode("utf-8"))["error"]["message"]
		except Exception:
			message = str(e.code)
		raise TranslationError(_("%(service)s returned an error: %(error)s") % {"service": ENGINE_NAMES["claude"], "error": message})
	except Exception as e:
		raise TranslationError(_("Could not connect to %(service)s: %(error)s") % {"service": ENGINE_NAMES["claude"], "error": e})
	translated = "".join(
		block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
	).strip()
	translated, detected = splitLanguageTag(translated)
	if not translated:
		raise TranslationError(_("%s returned an empty translation") % ENGINE_NAMES["claude"])
	return translated, detected


_LANGUAGE_TAG_RE = re.compile(r"\s*\[([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)\][ \t]*\n?")


def splitLanguageTag(text):
	"""Separates Claude's leading "[fr] " tag from the translation; (text, None) when there is no tag."""
	match = _LANGUAGE_TAG_RE.match(text)
	if not match:
		return text.strip(), None
	return text[match.end():].strip(), _normalizeDetected(match.group(1))


# DeepL: needs a key, free for 500,000 characters a month. Free keys end in ":fx".

_DEEPL_TARGETS = {"en": "EN-US", "pt": "PT-BR", "zh-CN": "ZH-HANS", "zh-TW": "ZH-HANT", "no": "NB"}


def deeplTarget(code):
	return _DEEPL_TARGETS.get(code, code.upper())


def deepl(text, target, apiKey, purpose="incoming", formal=True, timeout=15):
	if not apiKey:
		raise TranslationError(_("No DeepL API key has been entered; enter it in the add-on settings"))
	host = "api-free.deepl.com" if apiKey.endswith(":fx") else "api.deepl.com"
	params = {"text": text, "target_lang": deeplTarget(target)}
	if purpose == "outgoing" and formal:
		# "prefer_" variants are ignored, not refused, for languages without formality.
		params["formality"] = "prefer_more"
	request = urllib.request.Request(
		"https://%s/v2/translate" % host, data=urllib.parse.urlencode(params).encode("utf-8"),
		headers={
			"Authorization": "DeepL-Auth-Key " + apiKey,
			"User-Agent": USER_AGENT,
			"Content-Type": "application/x-www-form-urlencoded",
		},
	)
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			result = json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as e:
		if e.code == 403:
			raise TranslationError(_("The DeepL API key is not valid"))
		if e.code == 456:
			raise TranslationError(_("The DeepL monthly character limit has been used up"))
		raise TranslationError(_("%(service)s returned error %(code)d") % {"service": ENGINE_NAMES["deepl"], "code": e.code})
	except Exception as e:
		raise TranslationError(_("Could not connect to %(service)s: %(error)s") % {"service": ENGINE_NAMES["deepl"], "error": e})
	try:
		item = result["translations"][0]
		translated = item["text"]
	except (KeyError, IndexError, TypeError):
		raise TranslationError(_("Could not understand the response from %s") % ENGINE_NAMES["deepl"])
	if not translated:
		raise TranslationError(_("%s returned an empty translation") % ENGINE_NAMES["deepl"])
	return translated, _normalizeDetected(item.get("detected_source_language"))


def _translateWith(engine, text, target, source, apiKeys, model, purpose, formal):
	if engine == "claude":
		return claude(text, target, apiKeys.get("claude", ""), model, purpose, formal)
	if engine == "deepl":
		return deepl(text, target, apiKeys.get("deepl", ""), purpose, formal)
	if engine == "bing":
		return bing(text, target)
	if engine == "mymemory":
		return mymemory(text, target, source)
	return google(text, target)


# Protected terms are swapped for placeholders that every service leaves alone
# (tested: Google, Bing and MyMemory keep "ZQX0" intact in both directions).

PLACEHOLDER = "ZQX"
_PLACEHOLDER_RE = re.compile(PLACEHOLDER + r"\s*(\d+)", re.IGNORECASE)


def protect(text, terms):
	"""Replaces each protected term (case-insensitive) with a placeholder; returns (text, originals)."""
	originals = []

	def swap(match):
		originals.append(match.group(0))
		return "%s%d" % (PLACEHOLDER, len(originals) - 1)

	for term in sorted({t.strip() for t in terms if t.strip()}, key=len, reverse=True):
		text = re.sub(re.escape(term), swap, text, flags=re.IGNORECASE)
	return text, originals


def restore(text, originals):
	def back(match):
		index = int(match.group(1))
		return originals[index] if index < len(originals) else match.group(0)

	return _PLACEHOLDER_RE.sub(back, text) if originals else text


def translate(
	text, target, engine="google", source="auto", apiKeys=None, model="",
	purpose="incoming", formal=True, fallback=True, terms=(),
):
	"""Translates with the chosen engine; if it fails and fallback is on, tries the free engines in turn.

	apiKeys maps "claude" and "deepl" to their keys.
	Returns (translation, detected source language code or None).
	Raises the chosen engine's error when every engine fails.
	"""
	apiKeys = apiKeys or {}
	protected, originals = protect(text, terms)
	order = [engine]
	if fallback:
		order += [e for e in FREE_ENGINES if e != engine]
	firstError = None
	for current in order:
		try:
			translated, detected = _translateWith(current, protected, target, source, apiKeys, model, purpose, formal)
			return restore(translated, originals), detected
		except TranslationError as e:
			firstError = firstError or e
	raise firstError
