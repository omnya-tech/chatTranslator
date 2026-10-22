# -*- coding: utf-8 -*-
# Copyright (C) 2026 Omnya Technology
# This file is covered by the GNU General Public License, version 2. See the file LICENSE for details.
# The list of conversations the add-on has settings for: see them, switch translation
# on or off, change the other party's language, or forget them.

import addonHandler
import wx

from . import languages

addonHandler.initTranslation()


class ConversationsDialog(wx.Dialog):
	def __init__(self, parent, store, describe):
		"""store: the ConversationStore. describe(key): a readable name for a conversation key."""
		super().__init__(parent, title=_("Saved conversations"))
		self._store = store
		self._describe = describe
		self._keys = []
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(self, label=_("Conversations:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
		self._list = wx.ListBox(self, size=(620, 300))
		sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 10)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		for label, handler in (
			(_("Turn translation on or off"), self._onToggle),
			(_("Change language..."), self._onLanguage),
			(_("Delete"), self._onDelete),
		):
			button = wx.Button(self, label=label)
			button.Bind(wx.EVT_BUTTON, handler)
			buttons.Add(button, 0, wx.RIGHT, 8)
		buttons.Add(wx.Button(self, wx.ID_CANCEL, _("Close")))
		sizer.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
		self.SetSizerAndFit(sizer)
		self._refresh()
		self._list.SetFocus()

	def _refresh(self, select=0):
		self._keys = [key for key, _entry in self._store.conversations()]
		lines = []
		for key in self._keys:
			entry = self._store.get(key)
			lines.append(_("%(name)s: translation %(state)s, language %(language)s") % {
				"name": self._describe(key),
				"state": _("on") if entry["enabled"] else _("off"),
				"language": languages.displayName(entry["lang"]),
			})
		self._list.Set(lines or [_("No saved conversations")])
		self._list.SetSelection(min(select, max(len(lines) - 1, 0)))

	def _selected(self):
		index = self._list.GetSelection()
		if index == wx.NOT_FOUND or index >= len(self._keys):
			return None, 0
		return self._keys[index], index

	def _onToggle(self, evt):
		key, index = self._selected()
		if key:
			self._store.set(key, enabled=not self._store.get(key)["enabled"])
			self._refresh(index)
			self._list.SetFocus()

	def _onLanguage(self, evt):
		key, index = self._selected()
		if not key:
			return
		codes = languages.codes()
		dialog = wx.SingleChoiceDialog(
			self, _("What language does the other party use?"), _("Chat Translator"), languages.displayNames()
		)
		current = self._store.get(key)["lang"]
		if current in codes:
			dialog.SetSelection(codes.index(current))
		if dialog.ShowModal() == wx.ID_OK:
			self._store.set(key, lang=codes[dialog.GetSelection()], chosen=True)
		dialog.Destroy()
		self._refresh(index)
		self._list.SetFocus()

	def _onDelete(self, evt):
		key, index = self._selected()
		if key:
			self._store.delete(key)
			self._refresh(index)
			self._list.SetFocus()
