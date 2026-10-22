import json
import os
import tempfile
import unittest

from tests import PACKAGE_DIR  # noqa: F401  (sets up the package)
from chatTranslatorTest import store


class ConversationStoreTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.TemporaryDirectory()
		self.path = os.path.join(self.folder.name, "conversations.json")

	def tearDown(self):
		self.folder.cleanup()

	def open(self):
		return store.ConversationStore(self.path, lambda: "en")

	def test_unknown_conversation_is_off_in_the_default_language(self):
		self.assertEqual(self.open().get("app|window"), {"enabled": False, "lang": "en", "own": False})

	def test_settings_survive_reopening(self):
		self.open().set("app|window", enabled=True, lang="fr")
		self.assertEqual(self.open().get("app|window"), {"enabled": True, "lang": "fr", "own": False})

	def test_chat_follows_its_window_until_it_has_its_own_setting(self):
		s = self.open()
		s.set("app|window", enabled=True, lang="de")
		# Turning translation on from anywhere in the window must work in its message field;
		# "own" lets the caller treat a search box differently.
		self.assertEqual(s.get("app|window||Message"), {"enabled": True, "lang": "de", "own": False})
		s.set("app|window||Message", enabled=False)
		self.assertEqual(s.get("app|window||Message"), {"enabled": False, "lang": "de", "own": True})
		self.assertTrue(s.get("app|window")["enabled"])

	def test_saved_entries_do_not_carry_the_own_flag(self):
		self.open().set("app|window||Message", enabled=True)
		with open(self.path, encoding="utf-8") as f:
			self.assertNotIn("own", f.read())

	def test_chat_keeps_its_own_setting(self):
		s = self.open()
		s.set("app|window", enabled=False, lang="de")
		s.set("app|window||Message to Acme", enabled=True, lang="fr")
		self.assertEqual(s.get("app|window||Message to Acme"), {"enabled": True, "lang": "fr", "own": True})
		self.assertEqual(s.get("app|window"), {"enabled": False, "lang": "de", "own": False})

	def test_last_chat_of_a_window_is_remembered_across_reopening(self):
		self.open().set("app|window||Message to Acme", enabled=True)
		self.assertEqual(self.open().lastChat("app|window"), "app|window||Message to Acme")

	def test_knows_window(self):
		s = self.open()
		s.set("app|window||chat", enabled=True)
		self.assertTrue(s.knowsWindow("app|window"))
		self.assertFalse(s.knowsWindow("app|win"))
		self.assertFalse(s.knowsWindow("other|window"))

	def test_window_follows_its_program(self):
		s = self.open()
		s.set("app", enabled=True, lang="fr")
		self.assertEqual(s.get("app|Acme - App"), {"enabled": True, "lang": "fr", "own": False})
		self.assertEqual(s.get("app|Acme - App||Message"), {"enabled": True, "lang": "fr", "own": False})
		self.assertFalse(s.get("other|window")["enabled"])
		self.assertTrue(s.knowsWindow("app|New chat - App"))

	def test_set_program_overrides_every_chat_and_keeps_their_languages(self):
		s = self.open()
		s.set("app|Acme - App||Message", enabled=False, lang="de")
		s.set("app|Beta - App", enabled=False)
		s.set("other|window", enabled=False)
		s.setProgram("app|Acme - App||Message", True)
		self.assertEqual(s.get("app|Acme - App||Message"), {"enabled": True, "lang": "de", "own": True})
		self.assertTrue(s.get("app|Beta - App")["enabled"])
		self.assertTrue(s.get("app|Gamma - App")["enabled"])
		self.assertFalse(s.get("other|window")["enabled"])
		self.assertEqual(self.open().get("app")["enabled"], True)

	def test_set_program_keeps_each_chat_language(self):
		s = self.open()
		s.set("app|Acme - App", enabled=False, lang="de")
		s.setProgram("app|Beta - App", True)
		self.assertEqual(s.get("app|Acme - App")["lang"], "de")
		self.assertEqual(s.get("app|New - App"), {"enabled": True, "lang": "en", "own": False})

	def test_a_chosen_language_is_remembered_by_level(self):
		s = self.open()
		self.assertFalse(s.languageChosen("app|window||chat"))
		s.set("app|window", lang="fr", chosen=True)
		self.assertTrue(s.languageChosen("app|window||chat"))
		s.set("app|window", enabled=False)
		self.assertTrue(s.languageChosen("app|window"))
		s.set("app|window||chat", enabled=True)
		self.assertTrue(s.languageChosen("app|window||chat"))
		s.set("app|window||other", lang="de", chosen=False)
		self.assertFalse(s.languageChosen("app|window||other"))

	def test_conversations_lists_only_conversations(self):
		s = self.open()
		s.set("app|window||chat", enabled=True)
		s.set("app|other", lang="it")
		self.assertEqual([key for key, _entry in s.conversations()], ["app|window||chat", "app|other"])

	def test_delete_forgets_the_conversation_and_its_last_chat(self):
		s = self.open()
		s.set("app|window||chat", enabled=True)
		s.delete("app|window||chat")
		reopened = self.open()
		self.assertEqual(reopened.conversations(), [])
		self.assertIsNone(reopened.lastChat("app|window"))

	def test_damaged_file_gives_an_empty_working_store(self):
		for content in ("{ not json", "[1, 2, 3]", '"text"', '{"app|w": "oops", "app|ok": {"enabled": true}}'):
			with open(self.path, "w", encoding="utf-8") as f:
				f.write(content)
			s = self.open()
			self.assertFalse(s.get("app|w")["enabled"])
			s.set("app|new", enabled=True)
			self.assertTrue(self.open().get("app|new")["enabled"])

	def test_unreadable_file_is_kept_aside(self):
		with open(self.path, "w", encoding="utf-8") as f:
			f.write("{ not json")
		self.open().set("app|new", enabled=True)
		with open(self.path + ".damaged", encoding="utf-8") as f:
			self.assertEqual(f.read(), "{ not json")

	def test_no_temporary_file_is_left_behind(self):
		self.open().set("app|window", enabled=True)
		self.assertEqual(os.listdir(self.folder.name), ["conversations.json"])

	def test_conversation_title(self):
		self.assertEqual(store.conversationTitle("chrome|www.messenger.com/t/1||Message"), "www.messenger.com/t/1 - Message")


class HistoryTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.TemporaryDirectory()
		self.path = os.path.join(self.folder.name, "history.jsonl")
		self.keep = True

	def tearDown(self):
		self.folder.cleanup()

	def open(self, limit=2000):
		return store.History(self.path, lambda: self.keep, limit)

	def test_entries_come_back_in_order(self):
		h = self.open()
		h.add("out", "app|window", "مرحبا", "Hello", "en")
		h.add("in", "app|window", "Hi", "أهلا", "en")
		entries = self.open().entries()
		self.assertEqual([(e["direction"], e["original"], e["translation"]) for e in entries], [("out", "مرحبا", "Hello"), ("in", "Hi", "أهلا")])
		self.assertEqual(entries[0]["conversation"], "window")

	def test_nothing_is_kept_when_the_user_turned_it_off(self):
		self.keep = False
		self.open().add("out", "app|window", "a", "b", "en")
		self.assertEqual(self.open().entries(), [])

	def test_old_entries_are_trimmed(self):
		h = self.open(limit=8)
		for i in range(30):
			h.add("out", "app|window", "message %d" % i, "x", "en")
		entries = self.open().entries()
		self.assertLessEqual(len(entries), 10)
		self.assertEqual(entries[-1]["original"], "message 29")
		self.assertEqual(os.listdir(self.folder.name), ["history.jsonl"])

	def test_damaged_lines_are_skipped(self):
		self.open().add("out", "app|window", "a", "b", "en")
		with open(self.path, "a", encoding="utf-8") as f:
			f.write("{ broken\n")
		self.assertEqual(len(self.open().entries()), 1)

	def test_clear(self):
		h = self.open()
		h.add("out", "app|window", "a", "b", "en")
		h.clear()
		self.assertEqual(h.entries(), [])
		h.add("out", "app|window", "c", "d", "en")
		self.assertEqual(len(h.entries()), 1)


if __name__ == "__main__":
	unittest.main()
