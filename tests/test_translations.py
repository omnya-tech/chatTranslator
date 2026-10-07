import glob
import gettext
import io
import os
import unittest

import build


class TranslationFileTests(unittest.TestCase):
	def test_every_language_translates_every_string(self):
		messages = build.sourceMessages()
		self.assertGreater(len(messages), 50)
		poFiles = glob.glob(os.path.join(build.SOURCE, "locale", "*", "LC_MESSAGES", "nvda.po"))
		self.assertTrue(poFiles)
		for path in poFiles:
			translated = build.readPo(path)
			missing = [m for m in messages if m not in translated]
			self.assertEqual(missing, [], path)

	def test_placeholders_match_between_original_and_translation(self):
		pattern = __import__("re").compile(r"%(?:\(\w+\))?[sd]")
		for path in glob.glob(os.path.join(build.SOURCE, "locale", "*", "LC_MESSAGES", "nvda.po")):
			for original, translation in build.readPo(path).items():
				self.assertEqual(
					sorted(pattern.findall(original)), sorted(pattern.findall(translation)),
					"%s: %r" % (path, original),
				)

	def test_compiled_file_is_readable_by_gettext(self):
		path = os.path.join(build.SOURCE, "locale", "ar", "LC_MESSAGES", "nvda.po")
		mo = gettext.GNUTranslations(io.BytesIO(build.compileMo(build.readPo(path))))
		self.assertEqual(mo.gettext("Chat Translator"), "مترجم المحادثات")
		self.assertEqual(mo.gettext("Developed by %s") % "Omnya Technology", "تطوير: Omnya Technology")


if __name__ == "__main__":
	unittest.main()
