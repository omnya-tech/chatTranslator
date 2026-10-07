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

import json
import os
import queue
import re
import threading
import time

import addonHandler
import api
import config
import controlTypes
import core
import globalPluginHandler
import globalVars
import gui
import scriptHandler
import speech
import textInfos
import tones
import ui
import winUser
import wx
from keyboardHandler import KeyboardInputGesture
from logHandler import log
from scriptHandler import script
from speech.sayAll import SayAllHandler

from . import detect, languages, translators
from .settings import SECTION, ChatTranslatorPanel, apiKeys, conf, confspec, migrateApiKeys
from .settings import myLanguage as userLanguage

addonHandler.initTranslation()

STORE_PATH = os.path.join(globalVars.appArgs.configPath, "chatTranslator.json")
HISTORY_PATH = os.path.join(globalVars.appArgs.configPath, "chatTranslator_history.jsonl")
HISTORY_LIMIT = 2000
CACHE_LIMIT = 500
# Below this many letters, a detected language is too unreliable to switch the conversation to.
DETECTION_MIN_LETTERS = 12
CHAT_SEPARATOR = "||"
# Chat apps can take a while to show pasted text; check this often, for this long, before giving up.
PASTE_CHECK_INTERVAL = 150
PASTE_CHECK_LIMIT = 2000
# A send that has not finished after this long is assumed lost, so Enter is never blocked for good.
SENDING_TIMEOUT = 30
OBJECT_REPLACEMENT = "￼"
UNREAD_COUNT_RE = re.compile(r"\(\d+\)")
BIDI_MARKS_RE = re.compile("[‎‏‪-‮⁦-⁩]")


def windowKey():
	"""Identifies the window by app and title, without unread counts that change all the time."""
	fg = api.getForegroundObject()
	if not fg:
		return ""
	app = fg.appModule.appName if fg.appModule else ""
	title = BIDI_MARKS_RE.sub("", fg.name or "")
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
	if text and (name in text or text in name):
		# Some fields report their content as their name; that would change with every keystroke.
		return None
	return name


def conversationTitle(key):
	"""A readable name for a conversation key, for the history."""
	title = key.split("|", 1)[-1]
	return title.replace(CHAT_SEPARATOR, " - ")


def sendControlKey(letter):
	"""Presses Control plus a letter by its virtual key code.

	KeyboardInputGesture.fromName("control+a") looks the letter up in the active keyboard
	layout and fails when that layout (Arabic, for example) has no "a".
	"""
	vk = ord(letter.upper())
	KeyboardInputGesture(
		{(winUser.VK_CONTROL, False)}, vk, winUser.user32.MapVirtualKeyW(vk, 0), False
	).send()


def isEditable(obj):
	if not obj:
		return False
	states = obj.states
	if controlTypes.State.READONLY in states:
		return False
	return controlTypes.State.EDITABLE in states or obj.role == controlTypes.Role.EDITABLETEXT


class ConversationStore:
	"""Per-conversation {"enabled": bool, "lang": code}, kept in the NVDA config folder.

	A chat key ("window||chat label") falls back to its window's entry until the chat gets its own.
	"""

	def __init__(self):
		self._data = {}
		try:
			with open(STORE_PATH, encoding="utf-8") as f:
				self._data = json.load(f)
		except FileNotFoundError:
			pass
		except Exception:
			log.exception("chatTranslator: could not read %s", STORE_PATH)

	def get(self, key):
		entry = self._data.get(key)
		if entry is None:
			entry = self._data.get(key.split(CHAT_SEPARATOR)[0], {})
		return {
			"enabled": entry.get("enabled", False),
			"lang": entry.get("lang", conf()["defaultTargetLanguage"]),
		}

	def set(self, key, **values):
		entry = self.get(key)
		entry.update(values)
		self._data[key] = entry
		try:
			with open(STORE_PATH, "w", encoding="utf-8") as f:
				json.dump(self._data, f, ensure_ascii=False, indent=1)
		except Exception:
			log.exception("chatTranslator: could not write %s", STORE_PATH)


class History:
	"""Translated messages, one JSON object per line, trimmed to the last HISTORY_LIMIT."""

	def __init__(self):
		self._lock = threading.Lock()
		self._lines = None

	def add(self, direction, key, original, translation, lang):
		if not conf()["saveHistory"]:
			return
		entry = {
			"time": time.strftime("%Y-%m-%d %H:%M"),
			"direction": direction,
			"conversation": conversationTitle(key),
			"original": original,
			"translation": translation,
			"lang": lang,
		}
		with self._lock:
			try:
				if self._lines is None:
					self._lines = len(self._read())
				with open(HISTORY_PATH, "a", encoding="utf-8") as f:
					f.write(json.dumps(entry, ensure_ascii=False) + "\n")
				self._lines += 1
				if self._lines > HISTORY_LIMIT * 5 // 4:
					kept = self._read()[-HISTORY_LIMIT:]
					with open(HISTORY_PATH, "w", encoding="utf-8") as f:
						f.writelines(line + "\n" for line in kept)
					self._lines = len(kept)
			except Exception:
				log.exception("chatTranslator: could not write the history")

	@staticmethod
	def _read():
		try:
			with open(HISTORY_PATH, encoding="utf-8") as f:
				return [line.rstrip("\n") for line in f if line.strip()]
		except FileNotFoundError:
			return []

	def entries(self):
		with self._lock:
			result = []
			for line in self._read():
				try:
					result.append(json.loads(line))
				except ValueError:
					pass
			return result

	def clear(self):
		with self._lock:
			try:
				os.remove(HISTORY_PATH)
			except FileNotFoundError:
				pass
			self._lines = 0


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Chat Translator")

	def __init__(self):
		super().__init__()
		config.conf.spec[SECTION] = confspec
		migrateApiKeys()
		self._store = ConversationStore()
		self._history = History()
		ChatTranslatorPanel.clearHistory = self._history.clear
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
		# Preview mode: the translation waiting in the field for a second Enter.
		self._awaiting = None
		self._enterBound = False
		# Last chat key seen in each window, so speech elsewhere in the window uses that chat's setting.
		self._chatKeys = {}
		self._convKey = self._keyFor(api.getFocusObject())
		self._lastSelectionTranslation = None
		self._copyWhenReady = False
		self._worker = threading.Thread(target=self._incomingWorker, name="chatTranslator", daemon=True)
		self._worker.start()
		speech.extensions.filter_speechSequence.register(self._filterSpeech)
		speech.extensions.pre_speechCanceled.register(self._onSpeechCanceled)
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(ChatTranslatorPanel)
		self._updateEnterBinding(api.getFocusObject())

	def terminate(self):
		speech.extensions.filter_speechSequence.unregister(self._filterSpeech)
		speech.extensions.pre_speechCanceled.unregister(self._onSpeechCanceled)
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(ChatTranslatorPanel)
		except ValueError:
			pass
		self._jobs.put(None)
		super().terminate()

	# Shared helpers

	def _keyFor(self, obj):
		window = windowKey()
		if isEditable(obj):
			label = chatLabel(obj)
			key = window + CHAT_SEPARATOR + label if label else window
			self._chatKeys[window] = key
			return key
		return self._chatKeys.get(window, window)

	def _currentConversation(self):
		self._convKey = key = self._keyFor(api.getFocusObject())
		return key, self._store.get(key)

	def _translate(self, text, target, purpose, source=None):
		"""Returns (translation, detected language or None, came from cache)."""
		c = conf()
		engine = c["engine"]
		terms = tuple(c["protectedTerms"])
		if source is None:
			source = userLanguage() if purpose == "outgoing" else "auto"
		cacheKey = (engine, target, purpose, terms, text)
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
		)
		with self._cacheLock:
			self._cache[cacheKey] = (translated, detected)
			while len(self._cache) > CACHE_LIMIT:
				del self._cache[next(iter(self._cache))]
		return translated, detected, False

	def _cached(self, text, target, purpose):
		c = conf()
		with self._cacheLock:
			hit = self._cache.get((c["engine"], target, purpose, tuple(c["protectedTerms"]), text))
		return hit[0] if hit else None

	def _startSending(self):
		self._sending = True
		self._sendingSince = time.monotonic()

	def _busy(self):
		return self._sending and time.monotonic() - self._sendingSince < SENDING_TIMEOUT

	def _fieldStillFocused(self, obj):
		"""The focused message field if it is still obj's field, else None.

		Some chat apps rebuild the editor when its text changes, so the focus moves to a new
		object; it still counts as the same field when it is in the same window and chat.
		"""
		focus = api.getFocusObject()
		if focus == obj:
			return focus
		if (
			focus and isEditable(focus) and focus.windowHandle == obj.windowHandle
			and self._keyFor(focus) == self._keyFor(obj)
		):
			return focus
		return None

	def _say(self, text):
		"""Speaks text without the incoming filter translating it."""
		self._bypassFilter = True
		try:
			ui.message(text)
		finally:
			self._bypassFilter = False

	# Outgoing messages

	def event_gainFocus(self, obj, nextHandler):
		self._convKey = self._keyFor(obj)
		if self._awaiting and self._awaiting["obj"] != obj:
			self._awaiting = None
		self._updateEnterBinding(obj)
		nextHandler()

	def event_foreground(self, obj, nextHandler):
		self._convKey = self._keyFor(api.getFocusObject())
		self._updateEnterBinding(api.getFocusObject())
		nextHandler()

	def _updateEnterBinding(self, obj):
		want = False
		if conf()["enabled"] and conf()["translateOutgoing"] and isEditable(obj):
			want = self._store.get(self._convKey)["enabled"]
		if want and not self._enterBound:
			self.bindGesture("kb:enter", "translateAndSend")
			self._enterBound = True
		elif not want and self._enterBound:
			self.removeGestureBinding("kb:enter")
			self._enterBound = False

	def script_translateAndSend(self, gesture):
		if self._busy():
			# A message is already on its way; swallow repeated presses.
			return
		obj = api.getFocusObject()
		ti = obj.treeInterceptor
		if not isEditable(obj) or (ti and not ti.passThrough):
			gesture.send()
			return
		if self._awaiting and self._awaiting["obj"] == obj:
			self._confirmPreview(obj)
			return
		key, conversation = self._currentConversation()
		self._startSending()
		try:
			self._readFieldText(obj, lambda text, fromTextInfo: self._onFieldText(
				obj, gesture, text, fromTextInfo, conversation["lang"], key
			))
		except Exception as e:
			log.exception("chatTranslator: could not read the message field")
			self._sendFailed(str(e))

	def _confirmPreview(self, obj):
		awaiting = self._awaiting
		self._awaiting = None
		try:
			sent = obj.makeTextInfo(textInfos.POSITION_ALL).text
		except Exception:
			sent = awaiting["translation"]
		KeyboardInputGesture.fromName("enter").send()
		self._history.add("out", awaiting["key"], awaiting["original"], sent, awaiting["target"])
		ui.message(_("Sent"))

	def _readFieldText(self, obj, callback):
		"""Reads the field's text, falling back to the clipboard when the text has embedded objects such as emoji images."""
		try:
			text = obj.makeTextInfo(textInfos.POSITION_ALL).text
		except Exception:
			text = None
		if text is not None and OBJECT_REPLACEMENT not in text:
			callback(text, True)
			return
		saved = self._getClipboard()
		api.copyToClip("", notify=False)
		sendControlKey("a")
		sendControlKey("c")

		def read():
			copied = self._getClipboard() or ""
			self._restoreClipboard(saved)
			try:
				callback(copied, False)
			except Exception as e:
				log.exception("chatTranslator: could not read the message field")
				self._sendFailed(str(e))

		core.callLater(150, read)

	def _onFieldText(self, obj, gesture, text, fromTextInfo, target, key):
		if not text.strip():
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
				if backTranslate:
					try:
						meaning = self._translate(translated, myLanguage, "check", source=target)[0]
					except translators.TranslationError:
						# The message itself is fine; only the check is missing.
						meaning = None
			except translators.TranslationError as e:
				wx.CallAfter(self._sendFailed, str(e))
				return
			except Exception as e:
				log.exception("chatTranslator: outgoing translation failed")
				wx.CallAfter(self._sendFailed, str(e))
				return
			wx.CallAfter(self._pasteTranslation, {
				"obj": obj, "original": text, "fromTextInfo": fromTextInfo,
				"translation": translated, "meaning": meaning, "target": target, "key": key,
			})

		threading.Thread(target=work, daemon=True).start()

	def _sendFailed(self, message):
		log.info("chatTranslator: message not sent: translation or reading the field failed")
		self._sending = False
		tones.beep(220, 120)
		ui.message(_("The message was not sent. %s") % message)

	def _pasteTranslation(self, message):
		if not self._fieldStillFocused(message["obj"]):
			log.info("chatTranslator: message not sent: focus left the field during translation")
			self._sending = False
			ui.message(_("Sending was cancelled because you left the message field; your message is unchanged"))
			return
		saved = self._getClipboard()
		try:
			api.copyToClip(message["translation"], notify=False)
			sendControlKey("a")
			sendControlKey("v")
		except Exception as e:
			log.exception("chatTranslator: could not paste the translation")
			self._restoreClipboard(saved)
			self._sendFailed(str(e))
			return
		core.callLater(PASTE_CHECK_INTERVAL, self._afterPaste, message, saved, PASTE_CHECK_INTERVAL)

	def _afterPaste(self, message, savedClipboard, waited):
		finished = True
		try:
			obj = self._fieldStillFocused(message["obj"])
			if not obj:
				# Enter would land in whatever now has focus; leave the translation in the field instead.
				log.info("chatTranslator: message not sent: focus left the field after pasting")
				tones.beep(220, 120)
				ui.message(_("Sending was cancelled because you left the message field; the translation is in the field"))
				return
			if message["fromTextInfo"]:
				try:
					now = obj.makeTextInfo(textInfos.POSITION_ALL).text
				except Exception:
					now = None
				if now is not None and now.strip() == message["original"].strip():
					if waited < PASTE_CHECK_LIMIT:
						# The app has not shown the translation yet; look again shortly.
						finished = False
						core.callLater(PASTE_CHECK_INTERVAL, self._afterPaste, message, savedClipboard, waited + PASTE_CHECK_INTERVAL)
						return
					# The paste did not take; never send the untranslated text silently.
					log.info("chatTranslator: message not sent: the field still showed the original text after %d ms", waited)
					tones.beep(220, 120)
					ui.message(_("Could not put the translation in the message field, so the message was not sent"))
					return
			if conf()["previewBeforeSending"]:
				# Remember the field as it is now, in case the app rebuilt it.
				message["obj"] = obj
				self._awaiting = message
				parts = [message["translation"]]
				if message["meaning"]:
					parts.append(_("Meaning: %s") % message["meaning"])
				parts.append(_("Press Enter to send, or edit the message first"))
				self._say("\n".join(parts))
				return
			KeyboardInputGesture.fromName("enter").send()
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
	def _getClipboard():
		try:
			return api.getClipData()
		except Exception:
			return None

	@staticmethod
	def _restoreClipboard(saved):
		if saved is not None:
			try:
				api.copyToClip(saved, notify=False)
			except Exception:
				pass

	# Incoming messages

	def _needsTranslation(self, text, myLanguage):
		text = text.strip()
		letters = [ch for ch in text if ch.isalpha()]
		if len(letters) < 2:
			return False
		return not detect.isInLanguage(text, myLanguage)

	def _filterSpeech(self, speechSequence):
		if self._bypassFilter or self._sending:
			return speechSequence
		c = conf()
		if not c["enabled"] or not c["translateIncoming"] or not self._store.get(self._convKey)["enabled"]:
			return speechSequence
		myLanguage = userLanguage()
		foreign = [
			i for i, item in enumerate(speechSequence)
			if isinstance(item, str) and self._needsTranslation(item, myLanguage)
		]
		if not foreign and not self._pending:
			return speechSequence
		missing = [i for i in foreign if self._cached(speechSequence[i], myLanguage, "incoming") is None]
		if not missing and not self._pending:
			return self._applyCached(speechSequence, foreign, myLanguage)
		if SayAllHandler.isRunning():
			# Say all drives itself by callbacks in the sequence; holding it back would stall it.
			return self._applyCached(speechSequence, foreign, myLanguage)
		self._pending += 1
		self._jobs.put((self._generation, list(speechSequence), foreign, myLanguage, self._convKey))
		return []

	def _applyCached(self, speechSequence, indexes, target):
		result = list(speechSequence)
		for i in indexes:
			translated = self._cached(result[i], target, "incoming")
			if translated is not None:
				self._lastOriginal = result[i]
				result[i] = translated
		return result

	def _onSpeechCanceled(self):
		self._generation += 1
		self._pending = 0

	def _incomingWorker(self):
		while True:
			job = self._jobs.get()
			if job is None:
				return
			generation, sequence, indexes, target, key = job
			if generation != self._generation and (not conf()["autoDetectLanguage"] or not self._jobs.empty()):
				# Nobody will hear it. Language detection still wants it, but only the latest one:
				# skimming past many messages must not send each of them to the service.
				continue
			originals = {}
			failed = False
			# The detected language of the longest new text, for switching the conversation's language.
			detectedLanguage, detectedLength = None, 0
			for i in indexes:
				original = sequence[i]
				try:
					translated, detected, fromCache = self._translate(original, target, "incoming")
				except Exception as e:
					log.debugWarning("chatTranslator: incoming translation failed: %s" % e)
					failed = True
					continue
				originals[i] = original
				sequence[i] = translated
				letters = sum(ch.isalpha() for ch in original)
				# Short texts are mostly labels such as "Messages"; keep them out of the history and detection.
				if not fromCache and translated.strip() != original.strip() and letters >= DETECTION_MIN_LETTERS:
					self._history.add("in", key, original, translated, detected)
					if detected and letters > detectedLength:
						detectedLanguage, detectedLength = detected, letters
			wx.CallAfter(self._speakTranslated, generation, sequence, originals, failed)
			if detectedLanguage:
				# Even if the speech is cancelled, the conversation's language should still follow the message.
				wx.CallAfter(self._maybeSwitchLanguage, key, detectedLanguage, generation)

	def _speakTranslated(self, generation, sequence, originals, failed):
		if generation != self._generation:
			return
		self._pending = max(0, self._pending - 1)
		if originals:
			self._lastOriginal = "\n".join(originals.values())
		if failed:
			tones.beep(300, 60)
		self._bypassFilter = True
		try:
			speech.speech.speak(sequence)
		finally:
			self._bypassFilter = False

	def _maybeSwitchLanguage(self, key, detected, generation):
		c = conf()
		if not c["autoDetectLanguage"]:
			return
		if detected == userLanguage() or detected not in languages.codes():
			return
		if self._store.get(key)["lang"] == detected:
			return
		self._store.set(key, lang=detected)
		if generation == self._generation:
			self._say(_("The other party's language is now %s") % languages.displayName(detected))

	# Scripts

	def _reportIfAddonOff(self):
		if conf()["enabled"]:
			return False
		ui.message(_("Chat Translator is turned off"))
		return True

	@script(description=_("Turns Chat Translator on or off everywhere"), gesture="kb:NVDA+alt+shift+a")
	def script_toggleAddon(self, gesture):
		enabled = not conf()["enabled"]
		conf()["enabled"] = enabled
		if not enabled:
			# Drop any held-back speech so nothing translated is spoken after switching off.
			self._onSpeechCanceled()
			self._awaiting = None
		self._updateEnterBinding(api.getFocusObject())
		ui.message(_("Chat Translator on") if enabled else _("Chat Translator off"))

	@script(description=_("Turns translation on or off in the current conversation"), gesture="kb:NVDA+alt+shift+t")
	def script_toggle(self, gesture):
		if self._reportIfAddonOff():
			return
		key, conversation = self._currentConversation()
		enabled = not conversation["enabled"]
		self._store.set(key, enabled=enabled)
		if enabled:
			ui.message(_("Translation on, the other party's language is %s") % languages.displayName(conversation["lang"]))
		else:
			self._awaiting = None
			ui.message(_("Translation off"))
		self._updateEnterBinding(api.getFocusObject())

	@script(description=_("Chooses the other party's language in the current conversation"), gesture="kb:NVDA+alt+shift+l")
	def script_chooseLanguage(self, gesture):
		if self._reportIfAddonOff():
			return
		# Read the key now: once the dialog opens, the foreground window is the dialog.
		key, conversation = self._currentConversation()
		wx.CallAfter(self._showLanguageDialog, key, conversation["lang"])

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
		self._store.set(key, lang=lang, enabled=True)
		core.callLater(300, ui.message, _("Your messages will be sent in %s") % languages.displayName(lang))
		core.callLater(300, lambda: self._updateEnterBinding(api.getFocusObject()))

	@script(description=_("Sends the message as written, without translating it"), gesture="kb:NVDA+alt+shift+enter")
	def script_sendWithoutTranslation(self, gesture):
		obj = api.getFocusObject()
		if not isEditable(obj):
			ui.message(_("Not in a message field"))
			return
		self._awaiting = None
		KeyboardInputGesture.fromName("enter").send()
		ui.message(_("Sent without translation"))

	@script(
		description=_("Pastes the clipboard into the message field, translated into the other party's language"),
		gesture="kb:NVDA+alt+shift+v",
	)
	def script_pasteTranslated(self, gesture):
		if self._reportIfAddonOff():
			return
		obj = api.getFocusObject()
		if not isEditable(obj):
			ui.message(_("Not in a message field"))
			return
		text = self._getClipboard() or ""
		if not text.strip():
			ui.message(_("The clipboard is empty"))
			return
		if self._busy():
			return
		_key, conversation = self._currentConversation()
		target = conversation["lang"]
		self._startSending()
		tones.beep(880, 40)

		def work():
			try:
				translated = self._translate(text, target, "outgoing")[0]
			except Exception as e:
				wx.CallAfter(self._pasteTranslatedFailed, str(e))
				return
			wx.CallAfter(self._insertTranslation, obj, translated)

		threading.Thread(target=work, daemon=True).start()

	def _pasteTranslatedFailed(self, message):
		self._sending = False
		tones.beep(220, 120)
		ui.message(_("Translation failed. %s") % message)

	def _insertTranslation(self, obj, translated):
		"""Pastes at the caret, keeping whatever is already in the field; nothing is sent."""
		self._sending = False
		if not self._fieldStillFocused(obj):
			ui.message(_("Pasting was cancelled because you left the message field"))
			return
		saved = self._getClipboard()
		try:
			api.copyToClip(translated, notify=False)
			sendControlKey("v")
		finally:
			core.callLater(500, self._restoreClipboard, saved)
		self._say(translated)

	@script(description=_("Speaks the original text of the last translation"), gesture="kb:NVDA+alt+shift+o")
	def script_speakOriginal(self, gesture):
		if not self._lastOriginal:
			ui.message(_("Nothing has been translated yet"))
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
			ui.message(_("No text is selected and the clipboard is empty"))
			return
		_key, conversation = self._currentConversation()
		myLanguage = userLanguage()
		otherLanguage = conversation["lang"]
		self._lastSelectionTranslation = None
		self._copyWhenReady = False

		def work():
			try:
				# Text in my language goes to the other party's language; anything else comes to mine.
				if detect.isInLanguage(text, myLanguage):
					translated = self._translate(text, otherLanguage, "outgoing")[0]
				else:
					translated, detected, fromCache = self._translate(text, myLanguage, "incoming")
					if detected == myLanguage:
						translated = self._translate(text, otherLanguage, "outgoing")[0]
			except Exception as e:
				wx.CallAfter(ui.message, _("Translation failed. %s") % e)
				return
			wx.CallAfter(self._selectionTranslated, translated)

		threading.Thread(target=work, daemon=True).start()

	def _selectionTranslated(self, translated):
		self._lastSelectionTranslation = translated
		self._say(translated)
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
			ui.message(_("The history is empty"))
			return
		wx.CallAfter(self._showHistoryDialog, entries)

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

	@script(description=_("Reports the translation status of the current conversation"), gesture="kb:NVDA+alt+shift+s")
	def script_status(self, gesture):
		if self._reportIfAddonOff():
			return
		_key, conversation = self._currentConversation()
		engine = translators.ENGINE_NAMES.get(conf()["engine"], conf()["engine"])
		if conversation["enabled"]:
			ui.message(_(
				"Translation on, the other party's language is %(language)s, "
				"the translation service is %(service)s"
			) % {"language": languages.displayName(conversation["lang"]), "service": engine})
		else:
			ui.message(_("Translation is off in this conversation"))
