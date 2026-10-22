# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.

import addonHandler
import config
import gui
import languageHandler
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from logHandler import log

from . import credentials, languages
from .translators import CLAUDE_DEFAULT_MODEL, ENGINES, KEYED_ENGINES

addonHandler.initTranslation()

SECTION = "chatTranslator"
# Always shown in English, whatever NVDA's language.
DEVELOPER = "Omnya Technology"

confspec = {
	"enabled": "boolean(default=True)",
	"engine": 'option(%s, default="google")' % ", ".join('"%s"' % key for key, _label in ENGINES),
	# Only read to move keys saved by older builds into Credential Manager.
	"claudeApiKey": 'string(default="")',
	"claudeModel": 'string(default="%s")' % CLAUDE_DEFAULT_MODEL,
	"fallback": "boolean(default=True)",
	# Empty means NVDA's own language.
	"myLanguage": 'string(default="")',
	"defaultTargetLanguage": 'string(default="en")',
	"autoDetectLanguage": "boolean(default=False)",
	"translateOutgoing": "boolean(default=True)",
	"sendKey": 'option("enter", "control+enter", default="enter")',
	"previewBeforeSending": "boolean(default=False)",
	"backTranslate": "boolean(default=False)",
	"translateIncoming": "boolean(default=True)",
	"translateNotifications": "boolean(default=True)",
	"formalTone": "boolean(default=True)",
	"protectedTerms": "string_list(default=list())",
	"saveHistory": "boolean(default=True)",
}

# NVDA locale codes that differ from ours.
_NVDA_LANGUAGES = {"zh_CN": "zh-CN", "zh_TW": "zh-TW", "zh_HK": "zh-TW", "nb_NO": "no", "nn_NO": "no"}


def conf():
	return config.conf[SECTION]


def nvdaLanguage():
	"""NVDA's interface language as one of our codes, English when we do not offer it."""
	nvda = languageHandler.getLanguage()
	code = _NVDA_LANGUAGES.get(nvda, nvda.split("_")[0])
	return code if code in languages.codes() else "en"


def myLanguage():
	chosen = conf()["myLanguage"]
	return chosen if chosen in languages.codes() else nvdaLanguage()


# The keys that send a message, as the user sees them and as NVDA names them.
SEND_KEYS = (("enter", "Enter"), ("control+enter", "Control+Enter"))


def sendKeyName():
	return dict(SEND_KEYS).get(conf()["sendKey"], "Enter")


_apiKeys = {}


def apiKeys():
	"""The Claude and DeepL keys, read once from Credential Manager."""
	for engine in KEYED_ENGINES:
		if engine not in _apiKeys:
			try:
				_apiKeys[engine] = credentials.read(engine)
			except OSError:
				log.exception("chatTranslator: could not read the %s key", engine)
				_apiKeys[engine] = ""
	return dict(_apiKeys)


def setApiKey(engine, key):
	credentials.write(engine, key)
	_apiKeys[engine] = key


def migrateApiKeys():
	"""Moves a Claude key saved in nvda.ini by an older build into Credential Manager."""
	c = conf()
	if c["claudeApiKey"]:
		try:
			setApiKey("claude", c["claudeApiKey"])
			c["claudeApiKey"] = ""
		except OSError:
			log.exception("chatTranslator: could not move the Claude key to Credential Manager")


class ChatTranslatorPanel(SettingsPanel):
	title = _("Chat Translator")
	# Set by the global plugin, which owns the history file and the conversations.
	clearHistory = None
	showConversations = None

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		c = conf()
		engineKeys = [key for key, _label in ENGINES]
		keys = apiKeys()

		self.enabled = helper.addItem(wx.CheckBox(self, label=_("Enable Chat Translator")))
		self.enabled.SetValue(c["enabled"])

		self.engine = helper.addLabeledControl(
			_("Translation service:"), wx.Choice, choices=[label for _key, label in ENGINES]
		)
		self.engine.SetSelection(engineKeys.index(c["engine"]) if c["engine"] in engineKeys else 0)
		self.engine.Bind(wx.EVT_CHOICE, self._onEngineChange)

		# Settings for one service only, shown while that service is chosen.
		self.deeplSizer = wx.BoxSizer(wx.VERTICAL)
		deeplHelper = guiHelper.BoxSizerHelper(self, sizer=self.deeplSizer)
		self.deeplKey = deeplHelper.addLabeledControl(_("DeepL API key:"), wx.TextCtrl, style=wx.TE_PASSWORD)
		self.deeplKey.SetValue(keys["deepl"])
		helper.addItem(self.deeplSizer)

		self.claudeSizer = wx.BoxSizer(wx.VERTICAL)
		claudeHelper = guiHelper.BoxSizerHelper(self, sizer=self.claudeSizer)
		self.apiKey = claudeHelper.addLabeledControl(_("Claude API key:"), wx.TextCtrl, style=wx.TE_PASSWORD)
		self.apiKey.SetValue(keys["claude"])
		self.model = claudeHelper.addLabeledControl(_("Claude model:"), wx.TextCtrl)
		self.model.SetValue(c["claudeModel"])
		helper.addItem(self.claudeSizer)

		self.formalSizer = wx.BoxSizer(wx.VERTICAL)
		formalHelper = guiHelper.BoxSizerHelper(self, sizer=self.formalSizer)
		self.formalTone = formalHelper.addItem(
			wx.CheckBox(self, label=_("Write my messages in a formal tone suitable for businesses"))
		)
		self.formalTone.SetValue(c["formalTone"])
		helper.addItem(self.formalSizer)

		self.fallback = helper.addItem(
			wx.CheckBox(self, label=_("Automatically use another free service if the chosen one fails"))
		)
		self.fallback.SetValue(c["fallback"])

		names = languages.displayNames()
		codes = languages.codes()
		self.myLanguage = helper.addLabeledControl(
			_("My language (incoming messages are translated into it):"), wx.Choice,
			choices=[_("NVDA's language (%s)") % languages.displayName(nvdaLanguage())] + names,
		)
		self.myLanguage.SetSelection(codes.index(c["myLanguage"]) + 1 if c["myLanguage"] in codes else 0)

		self.defaultTarget = helper.addLabeledControl(_("Default language of the other party:"), wx.Choice, choices=names)
		self.defaultTarget.SetSelection(
			codes.index(c["defaultTargetLanguage"]) if c["defaultTargetLanguage"] in codes else 0
		)

		self.autoDetect = helper.addItem(
			wx.CheckBox(self, label=_("Detect the other party's language automatically from their messages"))
		)
		self.autoDetect.SetValue(c["autoDetectLanguage"])

		self.translateOutgoing = helper.addItem(
			wx.CheckBox(self, label=_("Translate my messages before sending them when I press Enter"))
		)
		self.translateOutgoing.SetValue(c["translateOutgoing"])

		self.sendKey = helper.addLabeledControl(
			_("The key that sends a message in my chat programs:"), wx.Choice,
			choices=[label for _key, label in SEND_KEYS],
		)
		self.sendKey.SetSelection([key for key, _label in SEND_KEYS].index(c["sendKey"]))

		self.preview = helper.addItem(
			wx.CheckBox(self, label=_("Let me hear the translation before sending; Enter again sends it"))
		)
		self.preview.SetValue(c["previewBeforeSending"])

		self.backTranslate = helper.addItem(
			wx.CheckBox(self, label=_("Translate my message back into my language so I can check its meaning"))
		)
		self.backTranslate.SetValue(c["backTranslate"])

		self.translateIncoming = helper.addItem(
			wx.CheckBox(self, label=_("Translate incoming messages when reading them"))
		)
		self.translateIncoming.SetValue(c["translateIncoming"])

		self.translateNotifications = helper.addItem(
			wx.CheckBox(self, label=_("Translate notifications of new messages"))
		)
		self.translateNotifications.SetValue(c["translateNotifications"])

		conversationsButton = helper.addItem(wx.Button(self, label=_("Saved conversations...")))
		conversationsButton.Bind(wx.EVT_BUTTON, self._onConversations)

		self.protectedTerms = helper.addLabeledControl(
			_("Words that must not be translated, such as company and product names (one per line):"),
			wx.TextCtrl, style=wx.TE_MULTILINE, size=(-1, 100),
		)
		self.protectedTerms.SetValue("\n".join(c["protectedTerms"]))

		self.saveHistory = helper.addItem(wx.CheckBox(self, label=_("Keep a history of translated messages")))
		self.saveHistory.SetValue(c["saveHistory"])
		clearButton = helper.addItem(wx.Button(self, label=_("Clear history")))
		clearButton.Bind(wx.EVT_BUTTON, self._onClearHistory)

		helper.addItem(wx.StaticText(self, label=_("Developed by %s") % DEVELOPER))

		self._updateServiceSettings()

	def _selectedEngine(self):
		return ENGINES[self.engine.GetSelection()][0]

	def _onEngineChange(self, evt):
		self._updateServiceSettings()

	def _updateServiceSettings(self):
		engine = self._selectedEngine()
		self.settingsSizer.Show(self.deeplSizer, engine == "deepl", recursive=True)
		self.settingsSizer.Show(self.claudeSizer, engine == "claude", recursive=True)
		self.settingsSizer.Show(self.formalSizer, engine in ("deepl", "claude"), recursive=True)
		self.Layout()
		parent = self.GetParent()
		if parent:
			parent.Layout()

	def _onConversations(self, evt):
		if ChatTranslatorPanel.showConversations:
			ChatTranslatorPanel.showConversations(self)

	def _onClearHistory(self, evt):
		if gui.messageBox(
			_("Delete all translated messages from the history?"), _("Clear history"),
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self,
		) != wx.YES:
			return
		if ChatTranslatorPanel.clearHistory:
			ChatTranslatorPanel.clearHistory()
		gui.messageBox(_("The history has been cleared"), _("Clear history"), wx.OK, self)

	def onSave(self):
		c = conf()
		codes = languages.codes()
		c["enabled"] = self.enabled.GetValue()
		c["engine"] = self._selectedEngine()
		for engine, field in (("claude", self.apiKey), ("deepl", self.deeplKey)):
			key = field.GetValue().strip()
			if key != apiKeys()[engine]:
				try:
					setApiKey(engine, key)
				except OSError:
					log.exception("chatTranslator: could not save the %s key", engine)
					gui.messageBox(_("The API key could not be saved"), _("Chat Translator"), wx.OK | wx.ICON_ERROR, self)
		c["claudeModel"] = self.model.GetValue().strip() or CLAUDE_DEFAULT_MODEL
		c["formalTone"] = self.formalTone.GetValue()
		c["fallback"] = self.fallback.GetValue()
		selection = self.myLanguage.GetSelection()
		c["myLanguage"] = codes[selection - 1] if selection > 0 else ""
		c["defaultTargetLanguage"] = codes[self.defaultTarget.GetSelection()]
		c["autoDetectLanguage"] = self.autoDetect.GetValue()
		c["translateOutgoing"] = self.translateOutgoing.GetValue()
		c["sendKey"] = SEND_KEYS[self.sendKey.GetSelection()][0]
		c["previewBeforeSending"] = self.preview.GetValue()
		c["backTranslate"] = self.backTranslate.GetValue()
		c["translateIncoming"] = self.translateIncoming.GetValue()
		c["translateNotifications"] = self.translateNotifications.GetValue()
		c["protectedTerms"] = [line.strip() for line in self.protectedTerms.GetValue().splitlines() if line.strip()]
		c["saveHistory"] = self.saveHistory.GetValue()
