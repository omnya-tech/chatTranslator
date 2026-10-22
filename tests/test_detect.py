import unittest

from tests import PACKAGE_DIR  # noqa: F401  (sets up the package)
from chatTranslatorTest import detect


class IsInLanguageTests(unittest.TestCase):
	def check(self, code, mine, foreign):
		for text in mine:
			self.assertTrue(detect.isInLanguage(text, code), "%s should count as %s" % (text, code))
		for text in foreign:
			self.assertFalse(detect.isInLanguage(text, code), "%s should not count as %s" % (text, code))

	def test_arabic(self):
		self.check(
			"ar",
			mine=["مرحبًا، كيف حالك؟", "رسالة من Acme اليوم", "زر"],
			foreign=["Thank you for contacting us", "Здравствуйте", "Hello"],
		)

	def test_english_user_hears_english_labels_without_delay(self):
		self.check(
			"en",
			mine=["button", "Send message", "Thank you for your order, we will reply soon", "Acme Support"],
			foreign=[
				"Bonjour, nous avons bien reçu votre demande",
				"Vielen Dank für Ihre Nachricht",
				"Gracias por su mensaje, le responderemos pronto",
				"مرحبا بك",
				"Спасибо",
			],
		)

	def test_french_user(self):
		self.check(
			"fr",
			mine=["Merci pour votre message", "bouton"],
			foreign=["Thank you for your message and your order", "شكرا لك"],
		)

	def test_languages_with_their_own_script(self):
		self.check("ru", mine=["Спасибо за сообщение"], foreign=["Thank you", "شكرا"])
		self.check("ko", mine=["감사합니다"], foreign=["ありがとうございます"])
		self.check("ja", mine=["ありがとうございます", "日本語"], foreign=["감사합니다"])
		self.check("zh-CN", mine=["谢谢你的消息"], foreign=["ありがとうございます", "Thank you"])

	def test_arabic_user_gets_persian_and_urdu_translated(self):
		self.check(
			"ar",
			mine=["مرحبًا، كيف حالك اليوم؟", "شكرا", "هذه رسالة عربية طويلة فيها كلمات كثيرة"],
			foreign=["سلام، حال شما چطور است؟ من خوبم", "آپ کیسے ہیں؟ میں ٹھیک ہوں، شکریہ"],
		)

	def test_persian_and_urdu_users(self):
		self.check("fa", mine=["سلام، حال شما چطور است؟"], foreign=["مرحبًا، كيف حالك اليوم؟ أتمنى أنك بخير", "آپ کیسے ہیں؟ میں ٹھیک ہوں"])
		self.check("ur", mine=["آپ کیسے ہیں؟ میں ٹھیک ہوں"], foreign=["مرحبًا، كيف حالك اليوم؟"])

	def test_russian_and_ukrainian_are_told_apart(self):
		self.check("ru", mine=["Спасибо, это очень хорошо"], foreign=["Дякую, це дуже добре, їжа смачна"])
		self.check("uk", mine=["Дякую, це дуже добре, їжа смачна"], foreign=["Спасибо, это очень хорошо"])

	def test_more_scripts(self):
		self.check("hy", mine=["Շնորհակալություն"], foreign=["Thank you"])
		self.check("ka", mine=["გმადლობთ"], foreign=["Спасибо"])
		self.check("ta", mine=["நன்றி"], foreign=["धन्यवाद"])
		self.check("am", mine=["አመሰግናለሁ"], foreign=["شكرا"])

	def test_user_of_a_latin_language_without_a_word_list_is_not_delayed(self):
		# Icelandic has no word list here: its own text must not be taken for foreign.
		self.assertTrue(detect.isInLanguage("Halló, hvernig hefur þú það í dag", "is"))
		self.assertTrue(detect.isInLanguage("hnappur", "is"))
		# Clear English still counts as foreign.
		self.assertFalse(detect.isInLanguage("Thank you for your message, we will reply soon", "is"))

	def test_more_latin_languages(self):
		self.check("hr", mine=["Hvala, kako ste? Ovo je za vas"], foreign=["Thank you for your message and your order"])
		self.check("en", mine=["Thank you for the order"], foreign=["Hvala, kako ste? Ovo je za vas i što se tiče"])

	def test_text_without_letters_needs_no_translation(self):
		self.assertTrue(detect.isInLanguage("12:30 ✓✓", "en"))
		self.assertTrue(detect.isInLanguage("", "ar"))

	def test_long_latin_text_with_no_known_words_is_foreign_to_an_english_user(self):
		self.assertFalse(detect.isInLanguage("Habari yako rafiki yangu mpendwa sana", "en"))


class SplitForeignTests(unittest.TestCase):
	def split(self, text, code="ar"):
		pieces = detect.splitForeign(text, code)
		self.assertEqual("".join(piece for piece, _foreign in pieces), text, "the text must come back whole")
		return pieces

	def test_message_after_a_prefix_in_my_language(self):
		self.assertEqual(
			self.split("تم استلام الرسالة 12:57 م بواسطة أحمد: Thanks, I will send it tomorrow"),
			[("تم استلام الرسالة 12:57 م بواسطة أحمد: ", False), ("Thanks, I will send it tomorrow", True)],
		)

	def test_short_message_after_a_long_prefix_is_still_found(self):
		pieces = self.split("تم استلام الرسالة 12:57 م بواسطة شركة التوريدات الدولية المحدودة: Thanks, will do")
		self.assertEqual(pieces[-1], ("Thanks, will do", True))

	def test_message_between_prefix_and_time(self):
		pieces = self.split("رسالة من أحمد، Hello, how are you today?، 3:15 م")
		self.assertEqual([foreign for _piece, foreign in pieces], [False, True, False])
		self.assertEqual(pieces[1][0], "Hello, how are you today?،")

	def test_a_lone_foreign_word_in_my_text_is_left_alone(self):
		self.assertEqual(self.split("أنا بستخدم WhatsApp على الكمبيوتر"), [("أنا بستخدم WhatsApp على الكمبيوتر", False)])
		self.assertEqual(self.split("تم الإرسال: OK"), [("تم الإرسال: OK", False)])

	def test_wholly_foreign_and_wholly_mine(self):
		self.assertEqual(self.split("Thank you for your order"), [("Thank you for your order", True)])
		self.assertEqual(self.split("مرحبا كيف حالك"), [("مرحبا كيف حالك", False)])
		self.assertEqual(self.split("12:30 ✓"), [("12:30 ✓", False)])

	def test_foreign_text_with_my_words_inside_stays_whole(self):
		text = "I met محمد yesterday at the office and عمر was there too"
		self.assertEqual(self.split(text), [(text, True)])

	def test_same_script_languages_are_judged_whole(self):
		text = "Message from Ahmed: Merci pour votre message, nous vous répondrons"
		self.assertEqual(len(self.split(text, "en")), 1)

	def test_latin_user_reading_another_script(self):
		pieces = self.split("Message from Ahmed: مرحبا كيف حالك اليوم", "en")
		self.assertEqual(pieces, [("Message from Ahmed: ", False), ("مرحبا كيف حالك اليوم", True)])


if __name__ == "__main__":
	unittest.main()
