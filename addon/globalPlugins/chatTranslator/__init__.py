# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Chat Translator: write in your own language, the message leaves in the other
# side's language; foreign messages are spoken to you translated.
#
# Outgoing: while translation is on for the current conversation and focus is in
# an editable field, Enter is taken over: the field text is translated, pasted
# over the original and then Enter is sent for real (or, in preview mode, on the
# next Enter).
# Incoming: a speech filter holds back any utterance with foreign text, translates
# it on a worker thread and speaks the result, keeping utterances in order.

import os
import queue
import re
import threading
import time
import urllib.parse

import addonHandler
import api
import braille
import config
import controlTypes
import core
import globalPluginHandler
import globalVars
import gui
import inputCore
import scriptHandler
import speech
import textInfos
import tones
import winUser
import wx
from keyboardHandler import KeyboardInputGesture
from logHandler import log
from scriptHandler import script
from speech.commands import LangChangeCommand
from speech.sayAll import SayAllHandler

from . import clipboard, detect, languages, translators
from .conversations import ConversationsDialog
from .store import CHAT_SEPARATOR, ConversationStore, History, appOf, conversationTitle, isProgramKey
from .settings import SECTION, ChatTranslatorPanel, apiKeys, conf, confspec, migrateApiKeys, sendKeyName
from .settings import myLanguage as userLanguage

addonHandler.initTranslation()

STORE_PATH = os.path.join(globalVars.appArgs.configPath, "chatTranslator.json")
HISTORY_PATH = os.path.join(globalVars.appArgs.configPath, "chatTranslator_history.jsonl")
HISTORY_LIMIT = 2000
CACHE_LIMIT = 500
# Below this many letters, a detected language is too unreliable to switch the conversation to.
DETECTION_MIN_LETTERS = 12
# Chat apps can take a while to show pasted text; check this often, for this long, before giving up.
PASTE_CHECK_INTERVAL = 150
PASTE_CHECK_LIMIT = 2000
# A send that has not finished after this long is assumed lost, so Enter is never blocked for good.
SENDING_TIMEOUT = 30
# Translating a message to send: seconds per service and seconds in all.
OUTGOING_TIMEOUT = 12
OUTGOING_BUDGET = 20
# How long to wait for an app to put the field's text on the clipboard.
CLIPBOARD_READ_LIMIT = 1500
# Speech waiting for a translation: seconds per service, seconds in all, and how long to
# stop trying after a failure so NVDA does not fall silent again and again while offline.
INCOMING_TIMEOUT = 4
INCOMING_BUDGET = 6
INCOMING_PAUSE = 30
# Speech this soon after a typed character is NVDA echoing what the user types.
TYPING_ECHO_SECONDS = 0.5
# Speech this soon after a Windows notification appears is that notification being read.
NOTIFICATION_SECONDS = 2
# What translated notifications are filed under in the history.
NOTIFICATIONS_KEY = "windows|Notifications"
# The gestures taken over for each choice of send key; the numeric keypad's Enter sends too.
SEND_GESTURES = {
	"enter": ("kb:enter", "kb:numpadEnter"),
	"control+enter": ("kb:control+enter", "kb:control+numpadEnter"),
}
# The add-on works in any program. This list only decides how a conversation is recognised: in a
# web browser by the page's address, because sites change the window title to announce messages;
# everywhere else, including programs built on web pages such as WhatsApp for desktop, by the
# window title, which is steady there. A browser missing from the list still works, by its title.
BROWSERS = {
	"chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "iexplore", "chromium", "waterfox",
	"librewolf", "floorp", "zen", "thorium", "palemoon", "seamonkey", "browser", "maxthon", "arc",
}
# With no way to see whether a paste took, wait this long (ms) before sending.
BLIND_PASTE_WAIT = 700
# Web and e-mail addresses, which are not text to translate.
ADDRESS_RE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+\.\S+")
# Clock times such as "12:30 PM", which are not worth a translation request each.
TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}(?::\d{2})?\s*(?:[AaPp]\.?[Mm]\b\.?)?")
OBJECT_REPLACEMENT = "\ufffc"
UNREAD_COUNT_RE = re.compile(r"\(\d+\)")
BIDI_MARKS_RE = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def documentAddress(obj):
	"""For an object in a web page, the page's address without query and fragment; else None."""
	try:
		ti = obj.treeInterceptor if obj else None
		url = getattr(ti, "documentConstantIdentifier", None) if ti else None
	except Exception:
		return None
	if not url or not isinstance(url, str):
		return None
	parts = urllib.parse.urlsplit(url)
	if parts.scheme not in ("http", "https", "file") or not (parts.netloc or parts.path):
		return None
	return (parts.netloc + parts.path).rstrip("/")


def windowKey(obj=None):
	"""Identifies the window obj (default: the focus) is in.

	For a page in a web browser this is the app and the page's address: sites change the page
	title to announce new messages, and sites such as Messenger give every chat its own address.
	Otherwise it is the app and the window title, without unread counts that change all the time.
	"""
	fg = api.getForegroundObject()
	if not fg:
		return ""
	try:
		app = fg.appModule.appName if fg.appModule else ""
		if app.lower() in BROWSERS:
			address = documentAddress(obj if obj is not None else api.getFocusObject())
			if address:
				return "%s|%s" % (app, address)
		title = BIDI_MARKS_RE.sub("", fg.name or "")
	except Exception:
		# The window's application may have just gone away.
		return ""
	title = " ".join(UNREAD_COUNT_RE.sub("", title).split())
	return "%s|%s" % (app, title)


def chatLabel(obj):
	"""The message field's own label, which in some apps names the chat ("Message to Acme").

	Where the label is the same for every chat it changes nothing; where it differs, each
	chat gets its own setting even though the window title is the same.
	"""
	try:
		name = BIDI_MARKS_RE.sub("", obj.name or "").strip()
	except Exception:
		return None
	if not name or len(name) > 100:
		return None
	try:
		text = obj.makeTextInfo(textInfos.POSITION_ALL).text.strip()
	except Exception:
		text = ""
	if text and name == text:
		# Some fields report their content as their name; that would change with every keystroke.
		# Only an exact match counts: a message such as "Ahmed" typed in a field labelled
		# "Message to Ahmed" must not make the label disappear.
		return None
	return name


def sendControlKey(letter):
	"""Presses Control plus a letter by its virtual key code.

	KeyboardInputGesture.fromName("control+a") looks the letter up in the active keyboard
	layout and fails when that layout (Arabic, for example) has no "a".
	"""
	vk = ord(letter.upper())
	KeyboardInputGesture(
		{(winUser.VK_CONTROL, False)}, vk, winUser.user32.MapVirtualKeyW(vk, 0), False
	).send()


def hasGraphics(obj, limit=300):
	"""Whether a message field holds images, such as emoji drawn as pictures.

	NVDA reports such an image as a mere space in the field's text, so the text alone would
	lose it; looks at no more than `limit` objects inside the field.
	"""
	try:
		# Asked for afresh: NVDA caches the property for a while, and a cached generator that
		# something else has already walked through would look like an empty field.
		for count, descendant in enumerate(obj._get_recursiveDescendants()):
			if descendant.role == controlTypes.Role.GRAPHIC:
				return True
			if count >= limit:
				break
	except Exception:
		pass
	return False


def isSearchField(obj):
	"""Best effort: whether an editable is a search box rather than a message field."""
	try:
		# NVDA itself classes the search boxes of Windows apps as SearchField.
		if any("SearchField" in cls.__name__ for cls in type(obj).__mro__):
			return True
		attributes = getattr(obj, "IA2Attributes", None) or {}
		if attributes.get("text-input-type") == "search" or "searchbox" in attributes.get("xml-roles", ""):
			return True
		return "search" in (getattr(obj, "UIAAutomationId", "") or "").lower()
	except Exception:
		return False


def isEditable(obj):
	if not obj:
		return False
	try:
		states = obj.states
		role = obj.role
	except Exception:
		# The object's application may have just gone away.
		return False
	if controlTypes.State.READONLY in states or controlTypes.State.PROTECTED in states:
		return False
	return controlTypes.State.EDITABLE in states or role == controlTypes.Role.EDITABLETEXT


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Chat Translator")

	def __init__(self):
		super().__init__()
		config.conf.spec[SECTION] = confspec
		migrateApiKeys()
		self._store = ConversationStore(STORE_PATH, lambda: conf()["defaultTargetLanguage"])
		self._history = History(HISTORY_PATH, lambda: conf()["saveHistory"], HISTORY_LIMIT)
		ChatTranslatorPanel.clearHistory = self._history.clear
		ChatTranslatorPanel.showConversations = self._showConversations
		self._cache = {}
		self._cacheLock = threading.Lock()
		# Incoming speech: utterances held back for translation, spoken in order.
		self._jobs = queue.Queue()
		self._generation = 0
		self._pending = 0
		self._bypassFilter = False
		self._lastOriginal = None
		# Outgoing: True while a message is being translated and sent.
		self._sending = False
		self._sendingSince = 0
		# Numbers each send, so a translation that arrives after its send was given up is ignored.
		self._sendId = 0
		# Preview mode: the translation waiting in the field for a second Enter.
		self._awaiting = None
		self._enterBound = False
		self._boundGestures = ()
		# Speech until this time (monotonic seconds) is a Windows notification being read.
		self._notificationUntil = 0
		# Last chat key seen in each window, so speech elsewhere in the window uses that chat's setting.
		self._chatKeys = {}
		self._convKey = self._keyFor(api.getFocusObject())
		self._lastSelectionTranslation = None
		self._copyWhenReady = False
		# Incoming translation is skipped until this time after a failure (monotonic seconds).
		self._incomingPausedUntil = 0
		self._lastTypedAt = 0
		# Automatic detection: the language last detected once in each conversation, waiting for a second message.
		self._detectedOnce = {}
		# True while one of the add-on's own dialogs is open.
		self._dialogOpen = False
		try:
			# Says which version a tester is running when they send their log.
			log.info("chatTranslator %s loaded" % addonHandler.getCodeAddon().version)
		except Exception:
			pass
		self._worker = threading.Thread(target=self._incomingWorker, name="chatTranslator", daemon=True)
		self._worker.start()
		speech.extensions.filter_speechSequence.register(self._filterSpeech)
		speech.extensions.pre_speechCanceled.register(self._onSpeechCanceled)
		inputCore.decide_executeGesture.register(self._noteTyping)
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(ChatTranslatorPanel)
		self._updateEnterBinding(api.getFocusObject())

	def terminate(self):
		speech.extensions.filter_speechSequence.unregister(self._filterSpeech)
		speech.extensions.pre_speechCanceled.unregister(self._onSpeechCanceled)
		inputCore.decide_executeGesture.unregister(self._noteTyping)
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(ChatTranslatorPanel)
		except ValueError:
			pass
		self._jobs.put(None)
		super().terminate()

	# Shared helpers

	def _keyFor(self, obj, force=False):
		"""The conversation key for obj's window, and chat when obj is a message field.

		Working out the chat reads the field's label and text, which is slow in a large document,
		so it is only done in windows where the add-on is in use, or when a command asks (force).
		"""
		window = windowKey(obj)
		if isEditable(obj) and (force or self._store.knowsWindow(window)):
			label = chatLabel(obj)
			key = window + CHAT_SEPARATOR + label if label else window
			if self._chatKeys.get(window) != key:
				self._chatKeys[window] = key
				if self._store.knowsWindow(window):
					self._store.rememberChat(window, key)
			return key
		return self._chatKeys.get(window) or self._store.lastChat(window) or window

	def _keyForFocus(self, force=False):
		"""The key of the field that has kept the focus, steady even if its label goes away.

		Some programs drop a field's label once text is typed in it. The field is still the same
		chat, so the key it had when focus arrived is kept rather than falling back to the
		window's setting, which could send a message untranslated.
		"""
		previous = self._convKey
		key = self._keyFor(api.getFocusObject(), force)
		if CHAT_SEPARATOR not in key and previous.startswith(key + CHAT_SEPARATOR):
			key = previous
			self._chatKeys[key.split(CHAT_SEPARATOR)[0]] = key
		return key

	def _currentConversation(self):
		self._convKey = key = self._keyForFocus(force=True)
		return key, self._store.get(key)

	def _noteTyping(self, gesture, *args, **kwargs):
		"""Records when a character is typed; never blocks the gesture."""
		if getattr(gesture, "isCharacter", False):
			self._lastTypedAt = time.monotonic()
		return True

	def _translate(self, text, target, purpose, source=None, quick=False):
		"""Returns (translation, detected language or None, came from cache).

		quick: give up fast, for speech that is being held back until the translation arrives.
		"""
		c = conf()
		engine = c["engine"]
		terms = tuple(c["protectedTerms"])
		if source is None:
			source = userLanguage() if purpose == "outgoing" else "auto"
		cacheKey = (engine, target, purpose, terms, c["formalTone"], text)
		with self._cacheLock:
			if cacheKey in self._cache:
				translated, detected = self._cache[cacheKey]
				return translated, detected, True
		translated, detected = translators.translate(
			text, target,
			engine=engine,
			source=source,
			fallback=c["fallback"],
			apiKeys=apiKeys(),
			model=c["claudeModel"],
			purpose=purpose,
			formal=c["formalTone"],
			terms=terms,
			timeout=INCOMING_TIMEOUT if quick else OUTGOING_TIMEOUT,
			budget=INCOMING_BUDGET if quick else OUTGOING_BUDGET,
		)
		with self._cacheLock:
			self._cache[cacheKey] = (translated, detected)
			while len(self._cache) > CACHE_LIMIT:
				del self._cache[next(iter(self._cache))]
		return translated, detected, False

	def _cached(self, text, target, purpose):
		c = conf()
		with self._cacheLock:
			hit = self._cache.get((c["engine"], target, purpose, tuple(c["protectedTerms"]), c["formalTone"], text))
		return hit[0] if hit else None

	def _startSending(self):
		self._sending = True
		self._sendingSince = time.monotonic()
		self._sendId += 1
		return self._sendId

	def _ifCurrent(self, sendId, function, *args):
		"""Runs function unless a newer send has started since the one numbered sendId."""
		if sendId == self._sendId:
			function(*args)

	def _takesOver(self, obj, conversation):
		"""Whether the send key should be taken over in obj, given its conversation's setting."""
		if not conversation["enabled"]:
			return False
		# A setting made for the whole window does not reach its search box.
		return conversation["own"] or not isSearchField(obj)

	def _busy(self):
		return self._sending and time.monotonic() - self._sendingSince < SENDING_TIMEOUT

	def _fieldStillFocused(self, obj, key):
		"""The focused message field if it is still the field obj of conversation key, else None.

		Some chat apps rebuild the editor when its text changes, so the focus moves to a new
		object; it still counts as the same field when it is in the same window and chat.
		The old object may be dead by then, so only its window handle is used.
		"""
		focus = api.getFocusObject()
		try:
			if focus == obj:
				return focus
			if (
				focus and isEditable(focus) and focus.windowHandle == obj.windowHandle
				and self._keyFor(focus, force=True) == key
			):
				return focus
		except Exception:
			log.debugWarning("chatTranslator: could not compare the focus with the message field", exc_info=True)
		return None

	def _say(self, text, language=None):
		"""Speaks text without the incoming filter translating it.

		language: the text's language code, so a synthesizer that switches voice by language
		reads it with the right one; None for text in the user's own language.
		"""
		self._sayParts([(text, language)])

	def _sayParts(self, parts):
		"""Speaks (text, language or None) pieces as one message, and shows them in braille."""
		sequence = []
		for text, language in parts:
			if language:
				sequence += [LangChangeCommand(languages.speechCode(language)), text, LangChangeCommand(None)]
			else:
				sequence.append(text)
		self._bypassFilter = True
		try:
			speech.speech.speak(sequence)
		finally:
			self._bypassFilter = False
		braille.handler.message("  ".join(text for text, _language in parts))

	@staticmethod
	def _inLanguage(sequence, indexes, language):
		"""Marks the strings at indexes as being in language.

		A translation replaces text the page may have tagged as, say, English; without this a
		synthesizer that switches voice by language would read the translation with that voice.
		"""
		code = languages.speechCode(language)
		result = []
		current = None
		for i, item in enumerate(sequence):
			if isinstance(item, LangChangeCommand):
				current = item.lang
			if i in indexes:
				result += [LangChangeCommand(code), item, LangChangeCommand(current)]
			else:
				result.append(item)
		return result

	def _pressSend(self):
		"""Presses the key that sends a message in the user's chat programs."""
		KeyboardInputGesture.fromName(conf()["sendKey"]).send()

	# Outgoing messages

	def event_gainFocus(self, obj, nextHandler):
		# Whatever goes wrong here, NVDA must still get the event, or it would not report the focus.
		try:
			if conf()["enabled"]:
				self._convKey = self._keyFor(obj)
				self._keepOrDropPreview(obj)
				self._updateEnterBinding(obj)
			elif self._boundGestures:
				self._updateEnterBinding(obj)
		except Exception:
			log.debugWarning("chatTranslator: focus handling failed", exc_info=True)
		nextHandler()

	def event_foreground(self, obj, nextHandler):
		try:
			if conf()["enabled"]:
				focus = api.getFocusObject()
				self._convKey = self._keyFor(focus)
				self._updateEnterBinding(focus)
		except Exception:
			log.debugWarning("chatTranslator: foreground handling failed", exc_info=True)
		nextHandler()

	def event_nameChange(self, obj, nextHandler):
		# Some programs keep the focus in the message field while the user switches chats, and only
		# change the field's label; without this the previous chat's setting would stay in force.
		try:
			if conf()["enabled"] and obj == api.getFocusObject():
				self._convKey = self._keyForFocus()
				self._keepOrDropPreview(obj)
				self._updateEnterBinding(obj)
		except Exception:
			log.debugWarning("chatTranslator: name change handling failed", exc_info=True)
		nextHandler()

	def event_UIA_window_windowOpen(self, obj, nextHandler):
		# A Windows notification (toast) arrives as a window opening; NVDA reads it next, wherever the focus is.
		try:
			if any("Toast" in cls.__name__ for cls in type(obj).__mro__):
				self._noteNotification()
		except Exception:
			log.debugWarning("chatTranslator: notification handling failed", exc_info=True)
		nextHandler()

	def event_alert(self, obj, nextHandler):
		# Notifications from browsers and some programs arrive as alerts.
		self._noteNotification()
		nextHandler()

	def _noteNotification(self):
		try:
			if conf()["enabled"] and conf()["translateNotifications"]:
				self._notificationUntil = time.monotonic() + NOTIFICATION_SECONDS
		except Exception:
			log.debugWarning("chatTranslator: notification handling failed", exc_info=True)

	def _keepOrDropPreview(self, obj):
		"""A waiting preview survives the app rebuilding its message field, and ends when focus really leaves."""
		awaiting = self._awaiting
		if not awaiting:
			return
		if awaiting["obj"] == obj:
			if self._convKey != awaiting["key"]:
				# Same field, but it now belongs to another chat.
				self._awaiting = None
			return
		if isEditable(obj) and obj.windowHandle == awaiting["obj"].windowHandle and self._convKey == awaiting["key"]:
			awaiting["obj"] = obj
		else:
			self._awaiting = None

	def _updateEnterBinding(self, obj):
		want = False
		if conf()["enabled"] and conf()["translateOutgoing"] and isEditable(obj):
			want = self._takesOver(obj, self._store.get(self._convKey))
		wanted = SEND_GESTURES.get(conf()["sendKey"], SEND_GESTURES["enter"]) if want else ()
		if wanted != self._boundGestures:
			for gesture in self._boundGestures:
				self.removeGestureBinding(gesture)
			for gesture in wanted:
				self.bindGesture(gesture, "translateAndSend")
			self._boundGestures = wanted
		self._enterBound = bool(wanted)

	def script_translateAndSend(self, gesture):
		if self._busy():
			# A message is already on its way; swallow repeated presses, audibly.
			tones.beep(660, 20)
			return
		obj = api.getFocusObject()
		ti = obj.treeInterceptor
		if ti and not ti.passThrough:
			# Browse mode: Enter activates what is under the cursor (here, it starts typing in the
			# field). Passing the key to the program instead could send the message as it is.
			activate = getattr(ti, "script_activatePosition", None)
			if activate:
				activate(gesture)
			else:
				gesture.send()
			return
		if not isEditable(obj):
			gesture.send()
			return
		key, conversation = self._currentConversation()
		if not self._takesOver(obj, conversation):
			# The key was still taken over from another field; this one is not for translating.
			gesture.send()
			return
		if self._awaiting and self._awaiting["obj"] == obj and self._confirmPreview(obj):
			return
		sendId = self._startSending()
		try:
			self._readFieldText(obj, lambda text, raw: self._onFieldText(
				obj, gesture, text, raw, conversation["lang"], key, sendId
			))
		except Exception as e:
			log.exception("chatTranslator: could not read the message field")
			self._sendFailed(str(e))

	def _confirmPreview(self, obj):
		"""Sends the previewed message; returns False when the field now holds a new message to translate."""
		awaiting = self._awaiting
		self._awaiting = None
		try:
			sent = obj.makeTextInfo(textInfos.POSITION_ALL).text
		except Exception:
			sent = awaiting["translation"]
		myLanguage = userLanguage()
		if (
			myLanguage != awaiting["target"] and sent.strip() != awaiting["translation"].strip()
			and any(ch.isalpha() for ch in sent) and detect.isInLanguage(sent, myLanguage)
			and not detect.isInLanguage(sent, awaiting["target"])
		):
			# The user discarded the translation and wrote something new in their own language.
			return False
		self._pressSend()
		self._history.add("out", awaiting["key"], awaiting["original"], sent, awaiting["target"])
		self._say(_("Sent"))
		return True

	def _readFieldText(self, obj, callback):
		"""Reads the message field and calls callback(text, raw).

		raw is the field's text as NVDA reports it, None when it cannot be read. Where the field
		holds images such as emoji, which that text leaves out, or cannot be read, text comes from
		copying the field: programs put an emoji on the clipboard as a character.
		"""
		try:
			raw = obj.makeTextInfo(textInfos.POSITION_ALL).text
		except Exception:
			raw = None
		if raw is not None and OBJECT_REPLACEMENT not in raw and not hasGraphics(obj):
			callback(raw, raw)
			return
		saved = self._getClipboard()
		# A marker shows when the app has really copied: an unchanged clipboard must never be
		# mistaken for the message, or whatever the user had copied earlier would be sent.
		marker = "\u2063chatTranslator %d\u2063" % time.monotonic_ns()
		self._copy(marker)
		sendControlKey("a")
		sendControlKey("c")

		def read(waited):
			copied = self._getClipboard()
			if (copied is None or copied == marker) and waited < CLIPBOARD_READ_LIMIT:
				core.callLater(100, read, waited + 100)
				return
			self._restoreClipboard(saved)
			try:
				# Copying selected the whole message; without this the user's next keystroke would replace it.
				KeyboardInputGesture.fromName("control+end").send()
				hasWords = raw is not None and any(ch.isalpha() for ch in raw)
				if copied is not None and copied != marker and hasWords and not any(ch.isalpha() for ch in copied):
					# The field has words but the copy brought none: do not trust it.
					copied = None
				if copied is None or copied == marker:
					if raw is not None and raw.strip():
						# There is a message but it could not be read; do not send it untranslated.
						log.info("chatTranslator: message not sent: the field could not be copied")
						self._sendFailed(_("Could not read the message field"))
						return
					copied = ""
				callback(copied, raw)
			except Exception as e:
				log.exception("chatTranslator: could not read the message field")
				self._sendFailed(str(e))

		core.callLater(100, read, 100)

	def _onFieldText(self, obj, gesture, text, raw, target, key, sendId):
		if not any(ch.isalpha() for ch in text):
			# Nothing to translate: an empty field, numbers, emoji.
			self._sending = False
			gesture.send()
			return
		tones.beep(880, 40)
		c = conf()
		myLanguage = userLanguage()
		backTranslate = c["backTranslate"]

		def work():
			try:
				translated = self._translate(text, target, "outgoing")[0]
				meaning = None
				if backTranslate and translated.strip() != text.strip():
					try:
						meaning = self._translate(translated, myLanguage, "check", source=target)[0]
					except translators.TranslationError:
						# The message itself is fine; only the check is missing.
						meaning = None
			except translators.TranslationError as e:
				wx.CallAfter(self._ifCurrent, sendId, self._sendFailed, str(e))
				return
			except Exception as e:
				log.exception("chatTranslator: outgoing translation failed")
				wx.CallAfter(self._ifCurrent, sendId, self._sendFailed, str(e))
				return
			wx.CallAfter(self._ifCurrent, sendId, self._pasteTranslation, {
				"obj": obj, "original": text, "fieldBefore": raw,
				"translation": translated, "meaning": meaning, "target": target, "key": key,
			})

		threading.Thread(target=work, daemon=True).start()

	def _sendFailed(self, message):
		log.info("chatTranslator: message not sent: translation or reading the field failed")
		self._sending = False
		tones.beep(220, 120)
		self._say(_("The message was not sent. %s") % message)

	def _pasteTranslation(self, message):
		if not self._fieldStillFocused(message["obj"], message["key"]):
			log.info("chatTranslator: message not sent: focus left the field during translation")
			self._sending = False
			self._say(_("Sending was cancelled because you left the message field; your message is unchanged"))
			return
		if message["translation"].strip() == message["original"].strip():
			# Already in the other party's language: send it as it is.
			self._sending = False
			self._pressSend()
			self._say(_("Sent"))
			return
		saved = self._getClipboard()
		try:
			self._copy(message["translation"])
			sendControlKey("a")
			sendControlKey("v")
		except Exception as e:
			log.exception("chatTranslator: could not paste the translation")
			self._restoreClipboard(saved)
			self._sendFailed(str(e))
			return
		# Where the field can be read, it is watched until the translation shows; where it
		# cannot, the only safeguard against sending the old text is to give the program time.
		wait = PASTE_CHECK_INTERVAL if message["fieldBefore"] is not None else BLIND_PASTE_WAIT
		core.callLater(wait, self._afterPaste, message, saved, wait)

	def _afterPaste(self, message, savedClipboard, waited):
		finished = True
		try:
			obj = self._fieldStillFocused(message["obj"], message["key"])
			if not obj:
				# Enter would land in whatever now has focus; leave the translation in the field instead.
				log.info("chatTranslator: message not sent: focus left the field after pasting")
				tones.beep(220, 120)
				self._say(_("Sending was cancelled because you left the message field; the translation is in the field"))
				return
			if message["fieldBefore"] is not None:
				try:
					now = obj.makeTextInfo(textInfos.POSITION_ALL).text
				except Exception:
					now = None
				if now is not None and now.strip() == message["fieldBefore"].strip():
					if waited < PASTE_CHECK_LIMIT:
						# The app has not shown the translation yet; look again shortly.
						finished = False
						core.callLater(PASTE_CHECK_INTERVAL, self._afterPaste, message, savedClipboard, waited + PASTE_CHECK_INTERVAL)
						return
					# The paste did not take; never send the untranslated text silently.
					log.info("chatTranslator: message not sent: the field still showed the original text after %d ms", waited)
					tones.beep(220, 120)
					KeyboardInputGesture.fromName("control+end").send()
					self._say(_("Could not put the translation in the message field, so the message was not sent"))
					return
			if conf()["previewBeforeSending"]:
				# Remember the field as it is now, in case the app rebuilt it.
				message["obj"] = obj
				self._awaiting = message
				parts = [(message["translation"], message["target"])]
				if message["meaning"]:
					parts.append((_("Meaning: %s") % message["meaning"], None))
				parts.append((_("Press %s to send, or edit the message first") % sendKeyName(), None))
				self._sayParts(parts)
				return
			self._pressSend()
			self._history.add("out", message["key"], message["original"], message["translation"], message["target"])
			report = _("Sent in %s") % languages.displayName(message["target"])
			if message["meaning"]:
				report += "\n" + _("Meaning: %s") % message["meaning"]
			self._say(report)
		finally:
			if finished:
				self._sending = False
				core.callLater(500, self._restoreClipboard, savedClipboard)

	@staticmethod
	def _copy(text):
		"""Puts the add-on's own text on the clipboard, kept out of the clipboard history where possible."""
		try:
			clipboard.copyPrivately(text, gui.mainFrame.Handle)
		except Exception:
			log.debugWarning("chatTranslator: private copy failed, copying normally", exc_info=True)
			api.copyToClip(text, notify=False)

	@staticmethod
	def _getClipboard():
		try:
			return api.getClipData()
		except Exception:
			return None

	@staticmethod
	def _restoreClipboard(saved):
		"""Puts back the text that was on the clipboard; when it held no text, empties it."""
		try:
			if saved is not None:
				api.copyToClip(saved, notify=False)
			else:
				with winUser.openClipboard(gui.mainFrame.Handle):
					winUser.emptyClipboard()
		except Exception:
			pass

	# Incoming messages

	@staticmethod
	def _hasWords(text):
		"""Whether text has something to translate once clock times and addresses are set aside."""
		text = TIME_RE.sub("", ADDRESS_RE.sub("", text))
		return sum(ch.isalpha() for ch in text) >= 2

	@staticmethod
	def _looksLikeName(piece):
		"""Whether piece is a name said before a message, such as a sender, a chat or a program
		("Digital Services," or "Google Chrome,"): translating a name only garbles it."""
		piece = piece.strip()
		if not piece.endswith((",", "،")):
			return False
		words = piece[:-1].split()
		return 0 < len(words) <= 3 and words[0][:1].isupper()

	def _foreignPieces(self, text, myLanguage):
		"""text as (piece, needs translating) pairs; a single (text, False) when nothing in it does."""
		if self._hasWords(text):
			pieces = [
				(piece, foreign and self._hasWords(piece) and not self._looksLikeName(piece))
				for piece, foreign in detect.splitForeign(text, myLanguage)
			]
			if any(foreign for _piece, foreign in pieces):
				return pieces
		return [(text, False)]

	def _needsTranslation(self, text, myLanguage):
		return any(foreign for _piece, foreign in self._foreignPieces(text, myLanguage))

	def _filterSpeech(self, speechSequence):
		try:
			return self._filter(speechSequence)
		except Exception:
			# Speech must go on whatever happens here.
			log.debugWarning("chatTranslator: speech filter failed", exc_info=True)
			return speechSequence

	def _filter(self, speechSequence):
		if self._bypassFilter or self._busy():
			return speechSequence
		c = conf()
		if not c["enabled"] or not c["translateIncoming"]:
			return speechSequence
		now = time.monotonic()
		key = self._convKey
		if not self._store.get(key)["enabled"]:
			if not (c["translateNotifications"] and now < self._notificationUntil):
				return speechSequence
			# A notification of a new message, read while the user is somewhere else.
			key = NOTIFICATIONS_KEY
		if now - self._lastTypedAt < TYPING_ECHO_SECONDS and isEditable(api.getFocusObject()):
			# NVDA echoing what the user is typing: say it as typed, at once.
			return speechSequence
		myLanguage = userLanguage()
		# Each string is cut into the pieces in the user's language and the foreign ones,
		# and only the foreign pieces go for translation.
		pieces = []
		foreign = []
		for item in speechSequence:
			if isinstance(item, str):
				for piece, isForeign in self._foreignPieces(item, myLanguage):
					if isForeign:
						foreign.append(len(pieces))
					pieces.append(piece)
			else:
				pieces.append(item)
		if not foreign and not self._pending:
			return speechSequence
		missing = [i for i in foreign if self._cached(pieces[i], myLanguage, "incoming") is None]
		if not missing and not self._pending:
			return self._applyCached(pieces, foreign, myLanguage)
		if now < self._incomingPausedUntil:
			# The service did not answer a moment ago; do not keep the user waiting again.
			return self._applyCached(pieces, foreign, myLanguage) if foreign else speechSequence
		if SayAllHandler.isRunning():
			# Say all drives itself by callbacks in the sequence; holding it back would stall it.
			return self._applyCached(pieces, foreign, myLanguage) if foreign else speechSequence
		self._pending += 1
		self._jobs.put((self._generation, pieces, foreign, myLanguage, key))
		return []

	def _applyCached(self, speechSequence, indexes, target):
		result = list(speechSequence)
		replaced = set()
		for i in indexes:
			translated = self._cached(result[i], target, "incoming")
			if translated is not None:
				self._lastOriginal = result[i]
				result[i] = translated
				replaced.add(i)
		return self._inLanguage(result, replaced, target) if replaced else result

	def _onSpeechCanceled(self):
		self._generation += 1
		self._pending = 0

	def _incomingWorker(self):
		while True:
			job = self._jobs.get()
			if job is None:
				return
			try:
				self._translateJob(*job)
			except Exception:
				# If this thread died, every later foreign utterance would be held back for ever.
				log.exception("chatTranslator: translating speech failed")
				generation, sequence = job[0], job[1]
				wx.CallAfter(self._speakTranslated, generation, sequence, {}, True, job[3])

	def _translateJob(self, generation, sequence, indexes, target, key):
		if generation != self._generation and (not conf()["autoDetectLanguage"] or not self._jobs.empty()):
			# Nobody will hear it. Language detection still wants it, but only the latest one:
			# skimming past many messages must not send each of them to the service.
			return
		originals = {}
		failed = False
		# The detected language of the longest new text, for switching the conversation's language.
		detectedLanguage, detectedLength = None, 0
		for i in indexes:
			original = sequence[i]
			try:
				translated, detected, fromCache = self._translate(original, target, "incoming", quick=True)
			except Exception as e:
				log.debugWarning("chatTranslator: incoming translation failed: %s" % e)
				failed = True
				self._incomingPausedUntil = time.monotonic() + INCOMING_PAUSE
				break
			originals[i] = original
			sequence[i] = translated
			letters = sum(ch.isalpha() for ch in original)
			# Short texts are mostly labels such as "Messages"; keep them out of the history and detection.
			if not fromCache and translated.strip() != original.strip() and letters >= DETECTION_MIN_LETTERS:
				self._history.add("in", key, original, translated, detected)
				if detected and letters > detectedLength:
					detectedLanguage, detectedLength = detected, letters
		wx.CallAfter(self._speakTranslated, generation, sequence, originals, failed, target)
		if detectedLanguage:
			# Even if the speech is cancelled, the conversation's language should still follow the message.
			wx.CallAfter(self._maybeSwitchLanguage, key, detectedLanguage, generation)

	def _speakTranslated(self, generation, sequence, originals, failed, language):
		if generation != self._generation:
			return
		self._pending = max(0, self._pending - 1)
		if originals:
			self._lastOriginal = "\n".join(originals.values())
			sequence = self._inLanguage(sequence, set(originals), language)
		if failed:
			tones.beep(300, 60)
		self._bypassFilter = True
		try:
			speech.speech.speak(sequence)
		finally:
			self._bypassFilter = False

	def _maybeSwitchLanguage(self, key, detected, generation):
		c = conf()
		if not c["autoDetectLanguage"] or key == NOTIFICATIONS_KEY:
			return
		if detected == userLanguage() or detected not in languages.codes():
			return
		if self._store.languageChosen(key):
			return
		if self._store.get(key)["lang"] == detected:
			self._detectedOnce.pop(key, None)
			return
		# One message is not enough: in a group a single member may write in another language.
		if self._detectedOnce.get(key) != detected:
			self._detectedOnce[key] = detected
			return
		del self._detectedOnce[key]
		self._store.set(key, lang=detected)
		if generation == self._generation:
			self._say(_("The other party's language is now %s") % languages.displayName(detected))

	# Scripts

	def _reportIfAddonOff(self):
		if conf()["enabled"] and windowKey():
			return False
		if conf()["enabled"]:
			# The window could not be identified (it may have just closed): say so rather than do nothing.
			self._say(_("Could not tell which conversation this is; try again"))
			return True
		self._say(_("Chat Translator is turned off"))
		return True

	@script(description=_("Turns Chat Translator on or off everywhere"), gesture="kb:NVDA+alt+shift+a")
	def script_toggleAddon(self, gesture):
		enabled = not conf()["enabled"]
		conf()["enabled"] = enabled
		if not enabled:
			# Drop any held-back speech so nothing translated is spoken after switching off.
			self._onSpeechCanceled()
			self._awaiting = None
		else:
			# Focus changes were not followed while the add-on was off.
			self._convKey = self._keyFor(api.getFocusObject())
		self._updateEnterBinding(api.getFocusObject())
		self._say(_("Chat Translator on") if enabled else _("Chat Translator off"))

	@script(
		description=_(
			"Turns translation on or off in the current conversation; "
			"pressed twice, in every conversation of the program"
		),
		gesture="kb:NVDA+alt+shift+t",
	)
	def script_toggle(self, gesture):
		if self._reportIfAddonOff():
			return
		key, conversation = self._currentConversation()
		if scriptHandler.getLastScriptRepeatCount() >= 1 and appOf(key):
			# The first press already switched this conversation; carry its new state to the whole program.
			self._store.setProgram(key, conversation["enabled"])
			if conversation["enabled"]:
				self._say(_("Translation on in all conversations of %s") % appOf(key))
			else:
				self._say(_("Translation off in all conversations of %s") % appOf(key))
			self._updateEnterBinding(api.getFocusObject())
			return
		enabled = not conversation["enabled"]
		self._store.set(key, enabled=enabled)
		if enabled:
			self._say(_("Translation on, the other party's language is %s") % languages.displayName(conversation["lang"]))
		else:
			self._awaiting = None
			self._say(_("Translation off"))
		self._updateEnterBinding(api.getFocusObject())

	@script(description=_("Chooses the other party's language in the current conversation"), gesture="kb:NVDA+alt+shift+l")
	def script_chooseLanguage(self, gesture):
		if self._reportIfAddonOff():
			return
		# Read the key now: once the dialog opens, the foreground window is the dialog.
		key, conversation = self._currentConversation()
		wx.CallAfter(self._oneDialog, self._showLanguageDialog, key, conversation["lang"])

	def _oneDialog(self, show, *args):
		"""Opens one of the add-on's dialogs unless one is open already: a second press of a command must not stack another."""
		if self._dialogOpen:
			return
		self._dialogOpen = True
		try:
			show(*args)
		finally:
			self._dialogOpen = False

	def _showLanguageDialog(self, key, current):
		codes = languages.codes()
		dialog = wx.SingleChoiceDialog(
			gui.mainFrame, _("What language does the other party use?"), _("Chat Translator"), languages.displayNames()
		)
		if current in codes:
			dialog.SetSelection(codes.index(current))
		gui.mainFrame.prePopup()
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			lang = codes[dialog.GetSelection()]
		finally:
			dialog.Destroy()
			gui.mainFrame.postPopup()
		# A language the user picked is kept: automatic detection does not change it.
		self._store.set(key, lang=lang, enabled=True, chosen=True)
		core.callLater(300, self._say, _("Your messages will be sent in %s") % languages.displayName(lang))
		core.callLater(300, lambda: self._updateEnterBinding(api.getFocusObject()))

	@script(description=_("Sends the message as written, without translating it"), gesture="kb:NVDA+alt+shift+enter")
	def script_sendWithoutTranslation(self, gesture):
		obj = api.getFocusObject()
		if not isEditable(obj):
			self._say(_("Not in a message field"))
			return
		self._awaiting = None
		self._pressSend()
		self._say(_("Sent without translation"))

	@script(
		description=_("Pastes the clipboard into the message field, translated into the other party's language"),
		gesture="kb:NVDA+alt+shift+v",
	)
	def script_pasteTranslated(self, gesture):
		if self._reportIfAddonOff():
			return
		obj = api.getFocusObject()
		if not isEditable(obj):
			self._say(_("Not in a message field"))
			return
		text = self._getClipboard() or ""
		if not text.strip():
			self._say(_("The clipboard is empty"))
			return
		if self._busy():
			return
		key, conversation = self._currentConversation()
		target = conversation["lang"]
		sendId = self._startSending()
		tones.beep(880, 40)

		def work():
			try:
				translated = self._translate(text, target, "outgoing")[0]
			except Exception as e:
				wx.CallAfter(self._ifCurrent, sendId, self._pasteTranslatedFailed, str(e))
				return
			wx.CallAfter(self._ifCurrent, sendId, self._insertTranslation, obj, key, translated)

		threading.Thread(target=work, daemon=True).start()

	def _pasteTranslatedFailed(self, message):
		self._sending = False
		tones.beep(220, 120)
		self._say(_("Translation failed. %s") % message)

	def _insertTranslation(self, obj, key, translated):
		"""Pastes at the caret, keeping whatever is already in the field; nothing is sent."""
		self._sending = False
		if not self._fieldStillFocused(obj, key):
			self._say(_("Pasting was cancelled because you left the message field"))
			return
		saved = self._getClipboard()
		try:
			self._copy(translated)
			sendControlKey("v")
		finally:
			core.callLater(500, self._restoreClipboard, saved)
		self._say(translated, self._store.get(key)["lang"])

	@script(description=_("Speaks the original text of the last translation"), gesture="kb:NVDA+alt+shift+o")
	def script_speakOriginal(self, gesture):
		if not self._lastOriginal:
			self._say(_("Nothing has been translated yet"))
			return
		self._say(self._lastOriginal)

	@script(
		description=_(
			"Translates the selected text, or the clipboard when nothing is selected; "
			"press twice to copy the translation"
		),
		gesture="kb:NVDA+alt+shift+c",
	)
	def script_translateSelection(self, gesture):
		if self._reportIfAddonOff():
			return
		if scriptHandler.getLastScriptRepeatCount() >= 1:
			if self._lastSelectionTranslation:
				self._copySelectionTranslation()
			else:
				self._copyWhenReady = True
			return
		text = self._selectedText() or self._getClipboard() or ""
		if not text.strip():
			self._say(_("No text is selected and the clipboard is empty"))
			return
		_key, conversation = self._currentConversation()
		myLanguage = userLanguage()
		otherLanguage = conversation["lang"]
		self._lastSelectionTranslation = None
		self._copyWhenReady = False

		def work():
			try:
				# Text in my language goes to the other party's language; anything else comes to mine.
				language = None
				if detect.isInLanguage(text, myLanguage):
					translated, language = self._translate(text, otherLanguage, "outgoing")[0], otherLanguage
				else:
					translated, detected, fromCache = self._translate(text, myLanguage, "incoming")
					if detected == myLanguage:
						translated, language = self._translate(text, otherLanguage, "outgoing")[0], otherLanguage
			except Exception as e:
				wx.CallAfter(self._say, _("Translation failed. %s") % e)
				return
			wx.CallAfter(self._selectionTranslated, translated, language)

		threading.Thread(target=work, daemon=True).start()

	def _selectionTranslated(self, translated, language):
		self._lastSelectionTranslation = translated
		self._say(translated, language)
		if self._copyWhenReady:
			self._copySelectionTranslation()

	def _copySelectionTranslation(self):
		self._copyWhenReady = False
		api.copyToClip(self._lastSelectionTranslation, notify=False)
		self._say(_("Translation copied"))

	@staticmethod
	def _selectedText():
		obj = api.getFocusObject()
		ti = obj.treeInterceptor
		source = ti if ti and not ti.passThrough else obj
		try:
			info = source.makeTextInfo(textInfos.POSITION_SELECTION)
		except Exception:
			return None
		if info.isCollapsed:
			return None
		return info.text

	@script(description=_("Shows the history of translated messages"), gesture="kb:NVDA+alt+shift+h")
	def script_showHistory(self, gesture):
		entries = self._history.entries()
		if not entries:
			self._say(_("The history is empty"))
			return
		wx.CallAfter(self._oneDialog, self._showHistoryDialog, entries)

	def _showHistoryDialog(self, entries):
		lines = []
		for entry in reversed(entries):
			direction = _("Sent") if entry.get("direction") == "out" else _("Received")
			lines.append("%s, %s, %s" % (direction, entry.get("conversation", ""), entry.get("time", "")))
			lines.append(_("Original: %s") % entry.get("original", ""))
			lines.append(_("Translation: %s") % entry.get("translation", ""))
			lines.append("")
		dialog = wx.Dialog(gui.mainFrame, title=_("Translation history"))
		sizer = wx.BoxSizer(wx.VERTICAL)
		text = wx.TextCtrl(dialog, value="\n".join(lines), style=wx.TE_MULTILINE | wx.TE_READONLY, size=(700, 450))
		sizer.Add(text, 1, wx.EXPAND | wx.ALL, 10)
		sizer.Add(wx.Button(dialog, wx.ID_CANCEL, _("Close")), 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
		dialog.SetSizerAndFit(sizer)
		text.SetFocus()
		gui.mainFrame.prePopup()
		try:
			dialog.ShowModal()
		finally:
			dialog.Destroy()
			gui.mainFrame.postPopup()

	@script(description=_("Shows the saved conversations and their settings"), gesture="kb:NVDA+alt+shift+m")
	def script_showConversations(self, gesture):
		wx.CallAfter(self._oneDialog, self._showConversations, None)

	def _showConversations(self, parent):
		"""parent: the settings panel when opened from there, None when opened by the command."""
		def describe(key):
			if isProgramKey(key):
				return _("All conversations of %s") % key
			return "%s (%s)" % (conversationTitle(key), appOf(key))

		dialog = ConversationsDialog(parent or gui.mainFrame, self._store, describe)
		if not parent:
			gui.mainFrame.prePopup()
		try:
			dialog.ShowModal()
		finally:
			dialog.Destroy()
			if not parent:
				gui.mainFrame.postPopup()
		# Settings may have changed for the conversation the user returns to.
		self._awaiting = None
		core.callLater(300, lambda: self._updateEnterBinding(api.getFocusObject()))

	@script(description=_("Reports the translation status of the current conversation"), gesture="kb:NVDA+alt+shift+s")
	def script_status(self, gesture):
		if self._reportIfAddonOff():
			return
		_key, conversation = self._currentConversation()
		engine = translators.ENGINE_NAMES.get(conf()["engine"], conf()["engine"])
		if conversation["enabled"]:
			self._say(_(
				"Translation on, the other party's language is %(language)s, "
				"the translation service is %(service)s"
			) % {"language": languages.displayName(conversation["lang"]), "service": engine})
		else:
			self._say(_("Translation is off in this conversation"))


if globalVars.appArgs.secure:
	# On the lock screen, sign-in and UAC screens the add-on does nothing at all.
	GlobalPlugin = globalPluginHandler.GlobalPlugin
