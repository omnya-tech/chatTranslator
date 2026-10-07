import unittest

from tests import PACKAGE_DIR  # noqa: F401  (sets up the package)
from chatTranslatorTest import translators


class ProtectedTermsTests(unittest.TestCase):
	def test_terms_become_placeholders_and_come_back(self):
		text, originals = translators.protect("I want Acme Pro from Acme", ["Acme Pro", "Acme"])
		self.assertNotIn("Acme", text)
		self.assertEqual(originals, ["Acme Pro", "Acme"])
		self.assertEqual(translators.restore(text, originals), "I want Acme Pro from Acme")

	def test_longer_term_wins_over_shorter_one_inside_it(self):
		text, originals = translators.protect("Acme Pro", ["Acme", "Acme Pro"])
		self.assertEqual(originals, ["Acme Pro"])

	def test_matching_ignores_case_but_keeps_the_written_form(self):
		text, originals = translators.protect("buy ACME pro now", ["Acme Pro"])
		self.assertEqual(translators.restore(text, originals), "buy ACME pro now")

	def test_placeholder_split_by_a_service_is_still_restored(self):
		# MyMemory sometimes inserts spaces inside tokens.
		self.assertEqual(translators.restore("طلب ZQX 0 جاهز", ["Acme"]), "طلب Acme جاهز")

	def test_blank_terms_are_ignored(self):
		self.assertEqual(translators.protect("hello", ["", "  "]), ("hello", []))


class ChunkTests(unittest.TestCase):
	def test_short_text_is_one_chunk(self):
		self.assertEqual(translators._chunks("hello", 10), ["hello"])

	def test_chunks_respect_the_limit_and_keep_all_text(self):
		text = "First sentence. Second sentence. Third one here."
		chunks = translators._chunks(text, 20)
		self.assertTrue(all(len(c) <= 20 for c in chunks))
		self.assertEqual("".join(chunks), text)

	def test_by_chunks_keeps_spacing_between_pieces(self):
		result = translators._byChunks("one. two. three.", 6, lambda chunk: chunk.upper())
		self.assertEqual(result, "ONE. TWO. THREE.")


class DetectedLanguageTests(unittest.TestCase):
	def test_service_codes_map_to_ours(self):
		cases = {
			"zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "nb": "no", "iw": "he",
			"en-GB": "en", "FR": "fr", "ZH": "zh-CN", "NB": "no", None: None, "": None, 5: None,
		}
		for given, expected in cases.items():
			self.assertEqual(translators._normalizeDetected(given), expected, given)


class FallbackTests(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.original = translators._translateWith

	def tearDown(self):
		translators._translateWith = self.original

	def fake(self, failing):
		def translateWith(engine, text, target, *args):
			self.calls.append(engine)
			if engine in failing:
				raise translators.TranslationError(engine + " failed")
			return text.upper(), "en"
		translators._translateWith = translateWith

	def test_falls_back_to_the_free_services_in_order(self):
		self.fake(failing={"claude", "google"})
		self.assertEqual(translators.translate("hi", "ar", engine="claude"), ("HI", "en"))
		self.assertEqual(self.calls, ["claude", "google", "bing"])

	def test_without_fallback_the_chosen_service_error_is_raised(self):
		self.fake(failing={"bing"})
		with self.assertRaisesRegex(translators.TranslationError, "bing failed"):
			translators.translate("hi", "ar", engine="bing", fallback=False)

	def test_when_everything_fails_the_first_error_is_reported(self):
		self.fake(failing={"google", "bing", "mymemory"})
		with self.assertRaisesRegex(translators.TranslationError, "bing failed"):
			translators.translate("hi", "ar", engine="bing")

	def test_protected_terms_survive_the_round_trip(self):
		self.fake(failing=set())
		translated, _detected = translators.translate("buy Acme now", "ar", terms=["Acme"])
		self.assertEqual(translated, "BUY Acme NOW")


class ClaudeLanguageTagTests(unittest.TestCase):
	def test_tag_is_split_from_the_translation(self):
		self.assertEqual(translators.splitLanguageTag("[fr] مرحبا"), ("مرحبا", "fr"))
		self.assertEqual(translators.splitLanguageTag("[zh-Hans]\n你好 world"), ("你好 world", "zh-CN"))

	def test_missing_tag_leaves_the_text_alone(self):
		self.assertEqual(translators.splitLanguageTag("  Hello [world]  "), ("Hello [world]", None))


class DeepLTests(unittest.TestCase):
	def test_target_codes(self):
		cases = {"en": "EN-US", "pt": "PT-BR", "zh-CN": "ZH-HANS", "zh-TW": "ZH-HANT", "no": "NB", "ar": "AR", "fr": "FR"}
		for ours, theirs in cases.items():
			self.assertEqual(translators.deeplTarget(ours), theirs)

	def test_missing_key_is_reported(self):
		with self.assertRaisesRegex(translators.TranslationError, "DeepL"):
			translators.deepl("hi", "ar", "")

	def test_keyed_services_are_not_used_as_free_fallbacks(self):
		self.assertFalse(set(translators.KEYED_ENGINES) & set(translators.FREE_ENGINES))


if __name__ == "__main__":
	unittest.main()
