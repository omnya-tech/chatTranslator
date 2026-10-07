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

	def test_text_without_letters_needs_no_translation(self):
		self.assertTrue(detect.isInLanguage("12:30 ✓✓", "en"))
		self.assertTrue(detect.isInLanguage("", "ar"))

	def test_long_latin_text_with_no_known_words_is_foreign_to_an_english_user(self):
		self.assertFalse(detect.isInLanguage("Habari yako rafiki yangu mpendwa sana", "en"))


if __name__ == "__main__":
	unittest.main()
