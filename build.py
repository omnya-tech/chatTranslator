# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# Builds the add-on.
#   python build.py        packs addon/ into chatTranslator-<version>.nvda-addon,
#                          compiling every locale/*/LC_MESSAGES/nvda.po to nvda.mo on the way
#   python build.py pot    writes chatTranslator.pot, the template translators start from
import ast
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "addon")
PACKAGE_DIR = os.path.join(SOURCE, "globalPlugins", "chatTranslator")


def manifestValue(key):
	with open(os.path.join(SOURCE, "manifest.ini"), encoding="utf-8") as f:
		return re.search(r"^%s\s*=\s*(\S+)" % key, f.read(), re.M).group(1)


def readPo(path):
	"""Returns {msgid: msgstr} from a .po file with single or multi-line strings and no plurals."""
	messages = {}
	msgid = msgstr = None
	current = None
	with open(path, encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if line.startswith("msgid "):
				if msgid is not None:
					messages[msgid] = msgstr
				msgid, msgstr, current = ast.literal_eval(line[6:]), "", "id"
			elif line.startswith("msgstr "):
				msgstr, current = ast.literal_eval(line[7:]), "str"
			elif line.startswith('"'):
				if current == "id":
					msgid += ast.literal_eval(line)
				elif current == "str":
					msgstr += ast.literal_eval(line)
	if msgid is not None:
		messages[msgid] = msgstr
	return {k: v for k, v in messages.items() if v}


def compileMo(messages):
	"""Builds a GNU gettext .mo file."""
	ids = sorted(messages)
	keys = b"".join(k.encode("utf-8") + b"\0" for k in ids)
	values = b"".join(messages[k].encode("utf-8") + b"\0" for k in ids)
	keyStart = 7 * 4 + 16 * len(ids)
	valueStart = keyStart + len(keys)
	keyTable, valueTable = [], []
	offset = 0
	for k in ids:
		length = len(k.encode("utf-8"))
		keyTable += [length, keyStart + offset]
		offset += length + 1
	offset = 0
	for k in ids:
		length = len(messages[k].encode("utf-8"))
		valueTable += [length, valueStart + offset]
		offset += length + 1
	header = struct.pack("Iiiiiii", 0x950412DE, 0, len(ids), 7 * 4, 7 * 4 + 8 * len(ids), 0, 0)
	return header + struct.pack("%di" % len(keyTable), *keyTable) + struct.pack(
		"%di" % len(valueTable), *valueTable
	) + keys + values


def sourceMessages():
	"""Every translatable string: each _("literal") in the code, plus the language names translated at run time."""
	messages = []
	for name in sorted(os.listdir(PACKAGE_DIR)):
		if not name.endswith(".py"):
			continue
		with open(os.path.join(PACKAGE_DIR, name), encoding="utf-8") as f:
			tree = ast.parse(f.read())
		for node in ast.walk(tree):
			if (
				isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_"
				and node.args and isinstance(node.args[0], ast.Constant)
				and node.args[0].value not in messages
			):
				messages.append(node.args[0].value)
		if name == "languages.py":
			namespace = {}
			exec(compile(tree, name, "exec"), namespace)
			messages += [english for _code, english in namespace["LANGUAGES"] if english not in messages]
	return messages


def writePot(path):
	def quote(text):
		return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

	lines = [
		"# Translation template for the Chat Translator NVDA add-on.",
		'msgid ""',
		'msgstr ""',
		'"Project-Id-Version: chatTranslator %s\\n"' % manifestValue("version"),
		'"MIME-Version: 1.0\\n"',
		'"Content-Type: text/plain; charset=UTF-8\\n"',
		'"Content-Transfer-Encoding: 8bit\\n"',
		"",
	]
	for message in sourceMessages():
		lines += ["msgid %s" % quote(message), 'msgstr ""', ""]
	with open(path, "w", encoding="utf-8", newline="\n") as f:
		f.write("\n".join(lines))
	return path


def build():
	target = os.path.join(HERE, "%s-%s.nvda-addon" % (manifestValue("name"), manifestValue("version")))
	with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
		for root, dirs, files in os.walk(SOURCE):
			dirs[:] = [d for d in dirs if d != "__pycache__"]
			for file in files:
				path = os.path.join(root, file)
				arcname = os.path.relpath(path, SOURCE)
				if file.endswith(".po"):
					z.writestr(arcname[:-3] + ".mo", compileMo(readPo(path)))
				elif not file.endswith((".mo", ".pyc")):
					z.write(path, arcname)
		# The GPL travels with every copy of the add-on.
		z.write(os.path.join(HERE, "LICENSE"), "COPYING.txt")
	return target


if __name__ == "__main__":
	if sys.argv[1:] == ["pot"]:
		print(writePot(os.path.join(HERE, "chatTranslator.pot")))
	else:
		print(build())
