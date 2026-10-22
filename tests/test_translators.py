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


class TimeLimitTests(unittest.TestCase):
	def setUp(self):
		self.original = translators._translateWith
		self.seen = []

	def tearDown(self):
		translators._translateWith = self.original

	def test_timeout_reaches_the_service(self):
		def translateWith(engine, text, target, source, apiKeys, model, purpose, formal, timeout=None):
			self.seen.append(timeout)
			return text, None
		translators._translateWith = translateWith
		translators.translate("hi", "ar", timeout=4)
		translators.translate("hi", "ar")
		self.assertEqual(self.seen, [4, None])

	def test_used_up_budget_stops_trying_other_services(self):
		def translateWith(engine, *args):
			self.seen.append(engine)
			raise translators.TranslationError(engine + " failed")
		translators._translateWith = translateWith
		with self.assertRaisesRegex(translators.TranslationError, "google failed"):
			translators.translate("hi", "ar", engine="google", budget=0)
		self.assertEqual(self.seen, ["google"])

	def test_without_a_budget_every_service_is_tried(self):
		def translateWith(engine, *args):
			self.seen.append(engine)
			raise translators.TranslationError(engine + " failed")
		translators._translateWith = translateWith
		with self.assertRaises(translators.TranslationError):
			translators.translate("hi", "ar", engine="google")
		self.assertEqual(self.seen, ["google", "bing", "mymemory"])


class ClaudeReplyTests(unittest.TestCase):
	def setUp(self):
		self.original = translators.urllib.request.urlopen

	def tearDown(self):
		translators.urllib.request.urlopen = self.original

	def reply(self, body):
		import io, json

		class Response(io.BytesIO):
			def __enter__(self):
				return self

			def __exit__(self, *args):
				return False

		translators.urllib.request.urlopen = lambda request, timeout=None: Response(json.dumps(body).encode("utf-8"))

	def test_reply_cut_off_at_the_length_limit_is_an_error(self):
		self.reply({"stop_reason": "max_tokens", "content": [{"type": "text", "text": "[ar] half a mess"}]})
		with self.assertRaisesRegex(translators.TranslationError, "too long"):
			translators.claude("long text", "en", "key")

	def test_complete_reply_gives_text_and_language(self):
		self.reply({"stop_reason": "end_turn", "content": [{"type": "text", "text": "[fr] مرحبا"}]})
		self.assertEqual(translators.claude("Bonjour", "ar", "key"), ("مرحبا", "fr"))


class LanguageListTests(unittest.TestCase):
	def test_codes_are_unique_and_named(self):
		from chatTranslatorTest import languages
		codes = languages.codes()
		self.assertEqual(len(codes), len(set(codes)))
		self.assertGreater(len(codes), 100)
		self.assertTrue(all(name for _code, name in languages.LANGUAGES))

	def test_speech_codes_use_underscores(self):
		from chatTranslatorTest import languages
		self.assertEqual(languages.speechCode("zh-CN"), "zh_CN")
		self.assertEqual(languages.speechCode("fr"), "fr")


class MyMemoryTests(unittest.TestCase):
	def setUp(self):
		self.original = translators._open

	def tearDown(self):
		translators._open = self.original

	def test_html_entities_in_the_answer_are_decoded(self):
		import json
		translators._open = lambda *args, **kwargs: json.dumps({
			"responseStatus": 200, "responseData": {"translatedText": "I don&#39;t know &amp; you?", "detectedLanguage": "ar"},
		})
		self.assertEqual(translators.mymemory("x", "en"), ("I don't know & you?", "ar"))


if __name__ == "__main__":
	unittest.main()
