import sys
import unittest

from tests import PACKAGE_DIR  # noqa: F401  (sets up the package)


@unittest.skipUnless(sys.platform == "win32", "Credential Manager exists only on Windows")
class CredentialTests(unittest.TestCase):
	NAME = "unittest"

	def setUp(self):
		from chatTranslatorTest import credentials
		self.credentials = credentials
		credentials.delete(self.NAME)

	def tearDown(self):
		self.credentials.delete(self.NAME)

	def test_round_trip(self):
		self.assertEqual(self.credentials.read(self.NAME), "")
		self.credentials.write(self.NAME, "sk-ant-مفتاح")
		self.assertEqual(self.credentials.read(self.NAME), "sk-ant-مفتاح")

	def test_writing_an_empty_key_deletes_it(self):
		self.credentials.write(self.NAME, "x")
		self.credentials.write(self.NAME, "")
		self.assertEqual(self.credentials.read(self.NAME), "")


if __name__ == "__main__":
	unittest.main()
