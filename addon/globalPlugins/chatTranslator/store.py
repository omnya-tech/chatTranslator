# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# What the add-on keeps on disk: the setting of each conversation, and the history of
# translated messages. Nothing here needs NVDA, so it can be tested on its own.

import json
import logging
import os
import threading
import time

try:
	from logHandler import log
except ImportError:
	log = logging.getLogger("chatTranslator")

CHAT_SEPARATOR = "||"
# Reserved key in the store: the last chat seen in each window.
LAST_CHAT_KEY = "__lastChat__"


def appOf(key):
	"""The program part of a conversation key: the key of the setting for the whole program."""
	return key.split("|", 1)[0]


def isProgramKey(key):
	return "|" not in key


def conversationTitle(key):
	"""A readable name for a conversation key, for the history."""
	title = key.split("|", 1)[-1]
	return title.replace(CHAT_SEPARATOR, " - ")


class ConversationStore:
	"""Per-conversation {"enabled": bool, "lang": code}, kept in the NVDA config folder.

	A chat key ("app|window||chat label") falls back to its window's entry until the chat gets
	its own, and a window to its program's entry ("app"): programs such as Telegram clients put
	the chat's name in the window title, so every chat is a window of its own.
	"""

	def __init__(self, path, defaultLanguage):
		"""path: the JSON file. defaultLanguage(): the language of a conversation that has none yet."""
		self._path = path
		self._defaultLanguage = defaultLanguage
		self._data = {}
		try:
			with open(path, encoding="utf-8") as f:
				data = json.load(f)
		except FileNotFoundError:
			return
		except Exception:
			log.exception("chatTranslator: could not read %s", path)
			# Keep the damaged file aside: the next save would otherwise write over it.
			try:
				os.replace(path, path + ".damaged")
			except OSError:
				pass
			return
		# Keep only what has the expected shape, whatever happened to the file.
		if isinstance(data, dict):
			self._data = {
				key: value for key, value in data.items()
				if isinstance(key, str) and isinstance(value, dict)
			}

	def get(self, key):
		"""The setting for a conversation.

		A chat follows its window until it has a setting of its own: turning translation on
		from anywhere in a window must work in its message field. "own" tells whether the
		setting was made for this very chat, rather than for the window as a whole.
		"""
		program = self._data.get(appOf(key), {})
		window = self._data.get(key.split(CHAT_SEPARATOR)[0], program)
		saved = key in self._data
		entry = self._data[key] if saved else window
		return {
			"enabled": bool(entry.get("enabled", False)),
			"lang": entry.get("lang") or window.get("lang") or program.get("lang") or self._defaultLanguage(),
			"own": saved and CHAT_SEPARATOR in key,
		}

	def set(self, key, **values):
		entry = self.get(key)
		del entry["own"]
		if self.languageChosen(key):
			# The language is carried over from where the user picked it, and so is that fact.
			entry["chosen"] = True
		entry.update(values)
		self._data[key] = entry
		if CHAT_SEPARATOR in key:
			self._data.setdefault(LAST_CHAT_KEY, {})[key.split(CHAT_SEPARATOR)[0]] = key
		self._save()

	def setProgram(self, key, enabled):
		"""Turns translation on or off in the whole program of conversation key: its own entry and
		every saved window and chat in it, so no older setting of a single chat goes against the
		user's choice. Each chat keeps its language; new ones start with the language of key."""
		app = appOf(key)
		program = self._data.setdefault(app, {})
		program["enabled"] = enabled
		program.setdefault("lang", self.get(key)["lang"])
		for other, saved in self._data.items():
			if other != LAST_CHAT_KEY and other != app and appOf(other) == app:
				saved["enabled"] = enabled
		self._save()

	def languageChosen(self, key):
		"""Whether the user picked this conversation's language, which automatic detection then leaves alone.

		The language comes from the chat, else its window, else its program; so does the answer.
		"""
		for level in (key, key.split(CHAT_SEPARATOR)[0], appOf(key)):
			if level in self._data:
				return bool(self._data[level].get("chosen"))
		return False

	def conversations(self):
		"""(key, entry) for every saved conversation, in the order they were added."""
		return [(key, entry) for key, entry in self._data.items() if key != LAST_CHAT_KEY]

	def delete(self, key):
		self._data.pop(key, None)
		chats = self._data.get(LAST_CHAT_KEY, {})
		for window in [w for w, chat in chats.items() if chat == key]:
			del chats[window]
		self._save()

	def knowsWindow(self, window):
		"""Whether the user has ever set anything for this window or a chat in it."""
		prefix = window + CHAT_SEPARATOR
		app = appOf(window)
		return any(
			key == window or key == app or key.startswith(prefix)
			for key in self._data if key != LAST_CHAT_KEY
		)

	def lastChat(self, window):
		"""The chat last seen in this window, so its setting applies before the message field is visited again."""
		return self._data.get(LAST_CHAT_KEY, {}).get(window)

	def rememberChat(self, window, key):
		chats = self._data.setdefault(LAST_CHAT_KEY, {})
		if chats.get(window) != key:
			chats[window] = key
			self._save()

	def _save(self):
		# Written beside the file and then swapped in, so a crash mid-write cannot destroy it.
		try:
			temporary = self._path + ".tmp"
			with open(temporary, "w", encoding="utf-8") as f:
				json.dump(self._data, f, ensure_ascii=False, indent=1)
			os.replace(temporary, self._path)
		except Exception:
			log.exception("chatTranslator: could not write %s", self._path)


class History:
	"""Translated messages, one JSON object per line, trimmed to the last `limit`."""

	def __init__(self, path, enabled, limit=2000):
		"""path: the file. enabled(): whether the user wants a history kept. limit: messages kept."""
		self._path = path
		self._enabled = enabled
		self._limit = limit
		self._lock = threading.Lock()
		self._lines = None

	def add(self, direction, key, original, translation, lang):
		if not self._enabled():
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
				with open(self._path, "a", encoding="utf-8") as f:
					f.write(json.dumps(entry, ensure_ascii=False) + "\n")
				self._lines += 1
				if self._lines > self._limit * 5 // 4:
					kept = self._read()[-self._limit:]
					temporary = self._path + ".tmp"
					with open(temporary, "w", encoding="utf-8") as f:
						f.writelines(line + "\n" for line in kept)
					os.replace(temporary, self._path)
					self._lines = len(kept)
			except Exception:
				log.exception("chatTranslator: could not write the history")

	def _read(self):
		try:
			with open(self._path, encoding="utf-8") as f:
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
				os.remove(self._path)
			except FileNotFoundError:
				pass
			self._lines = 0
