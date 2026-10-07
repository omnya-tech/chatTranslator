# مترجم المحادثات (Chat Translator)

إضافة لقارئ الشاشة NVDA تتيح لك مراسلة الشركات والمؤسسات الأجنبية بلغتك: تكتب رسالتك بالعربية وتضغط Enter، فتُرسَل مترجمةً إلى لغة الطرف الآخر. وحين يردّ عليك بلغته، يقرأ لك NVDA ردّه مترجمًا إلى العربية.

تطوير: Omnya Technology

[English below](#english)

## المزايا

- تعمل في واتساب وتيليجرام ويونيجرام لسطح المكتب، وفي المتصفح على ماسنجر وفيسبوك وواتساب ويب، وفي أي خانة كتابة.
- خمس خدمات ترجمة: جوجل ومايكروسوفت Bing وMyMemory مجانًا ودون تسجيل، وDeepL بمفتاح مجاني، وClaude لترجمة أدق بأسلوب رسمي. وإذا تعذّرت خدمة، انتقلت الإضافة إلى غيرها تلقائيًا.
- نطق الترجمة قبل الإرسال، والترجمة العكسية للتأكد من المعنى.
- كلمات لا تُترجَم، كأسماء الشركات والمنتجات.
- التعرّف التلقائي على لغة الطرف الآخر من رسائله.
- ترجمة أي نص محدد أو منسوخ في أي برنامج.
- سجل للرسائل المترجَمة.
- لا تُرسَل رسالتك أبدًا دون ترجمة إذا فشلت الترجمة.
- تظهر واجهتها بالعربية أو الإنجليزية حسب لغة NVDA، وتصلح لمستخدمي أي لغة من لغاتها الأربع والثلاثين.
- تُحفَظ مفاتيح DeepL وClaude في مدير بيانات الاعتماد في ويندوز.

## التثبيت

حمّل ملف `chatTranslator-x.y.z.nvda-addon` من صفحة [الإصدارات](../../releases)، ثم افتحه وNVDA يعمل، ووافق على التثبيت. تتطلّب الإضافة NVDA 2025.1 أو أحدث، واتصالًا بالإنترنت.

## الاختصارات

| الاختصار | الوظيفة |
|---|---|
| NVDA+Alt+Shift+A | تشغيل الإضافة كلها أو إيقافها |
| NVDA+Alt+Shift+T | تفعيل الترجمة في المحادثة الحالية أو إيقافها |
| NVDA+Alt+Shift+L | اختيار لغة الطرف الآخر |
| NVDA+Alt+Shift+Enter | إرسال الرسالة دون ترجمة |
| NVDA+Alt+Shift+V | لصق محتوى الحافظة مترجمًا في خانة الكتابة |
| NVDA+Alt+Shift+O | نطق النص الأصلي لآخر ما تُرجِم |
| NVDA+Alt+Shift+C | ترجمة النص المحدد أو الحافظة، والضغط مرتين ينسخ الترجمة |
| NVDA+Alt+Shift+H | سجل الرسائل المترجَمة |
| NVDA+Alt+Shift+S | حالة الترجمة |

الشرح الكامل للإضافة وإعداداتها في [الدليل العربي](addon/doc/ar/readme.html)، ويمكن فتحه أيضًا من مدير الإضافات في NVDA.

## للمطورين

```
python -m unittest discover -s tests -t .
python build.py
```

يُنشئ الأمر الثاني ملف `chatTranslator-<الإصدار>.nvda-addon` في مجلد المستودع، بعد تحويل ملفات الترجمة إلى الصيغة التي يقرؤها NVDA. ولا يحتاج أيٌّ من الأمرين إلى NVDA ولا إلى الإنترنت.

لإصدار نسخة جديدة: غيّر رقم الإصدار في `addon/manifest.ini`، وأضف التغييرات إلى `CHANGELOG.md`، ثم ادفع وسمًا بالرقم نفسه، مثل `v1.2.0`. فيبني GitHub الإضافة وينشرها في صفحة الإصدارات تلقائيًا.

### بنية المستودع

- `addon/globalPlugins/chatTranslator/__init__.py`: الإضافة نفسها، أي اعتراض Enter وتصفية كلام NVDA والاختصارات.
- `addon/globalPlugins/chatTranslator/translators.py`: خدمات الترجمة، ولا يعتمد على NVDA.
- `addon/globalPlugins/chatTranslator/settings.py`: صفحة الإعدادات.
- `addon/globalPlugins/chatTranslator/languages.py`: قائمة اللغات.
- `addon/globalPlugins/chatTranslator/detect.py`: معرفة لغة النص دون إنترنت، ولا يعتمد على NVDA.
- `addon/globalPlugins/chatTranslator/credentials.py`: حفظ المفاتيح في مدير بيانات الاعتماد في ويندوز.
- `addon/locale/`: ملفات الترجمة.
- `addon/doc/`: دليل المستخدم بالعربية والإنجليزية.
- `tests/`: اختبارات تعمل دون NVDA.

## الترجمة إلى لغات أخرى

نرحّب بترجمة الإضافة إلى أي لغة:

1. شغّل `python build.py pot` لإنشاء ملف `chatTranslator.pot`.
2. انسخه إلى `addon/locale/<رمز اللغة>/LC_MESSAGES/nvda.po`، مثل `addon/locale/fr/LC_MESSAGES/nvda.po`، وترجم فيه كل سطر `msgstr`.
3. ترجم الدليل إلى `addon/doc/<رمز اللغة>/readme.html`، ووصف الإضافة إلى `addon/locale/<رمز اللغة>/manifest.ini`.
4. شغّل الاختبارات، فهي تتأكد من ترجمة كل النصوص ومن تطابق علامات مثل `%s` بين الأصل والترجمة.

## الرخصة

رخصة جنو العمومية العامة، الإصدار الثاني (GPL v2)، وهي رخصة NVDA نفسه. انظر ملف [LICENSE](LICENSE).

---

<a id="english"></a>

# Chat Translator

An NVDA add-on for writing to foreign companies and organisations in your own language: type your message and press Enter, and it is sent translated into the other party's language. When they reply in their language, NVDA reads the reply to you translated into yours.

Developed by Omnya Technology

## Features

- Works in WhatsApp, Telegram and Unigram for desktop, in the browser on Messenger, Facebook and WhatsApp Web, and in any text field.
- Five translation services: Google, Microsoft Bing and MyMemory, free and without sign-up, DeepL with a free key, and Claude for more accurate, formal translation. If a service fails, the add-on switches to another automatically.
- Hear the translation before sending, and back-translation to check the meaning.
- Words that must not be translated, such as company and product names.
- Automatic detection of the other party's language from their messages.
- Translate any selected or copied text in any program.
- History of translated messages.
- Your message is never sent untranslated if translation fails.
- The interface follows NVDA's language (Arabic or English), and it works for speakers of any of its 34 languages.
- The DeepL and Claude keys are stored in Windows Credential Manager.

## Installation

Download `chatTranslator-x.y.z.nvda-addon` from the [releases page](../../releases), open it while NVDA is running and accept the installation. Requires NVDA 2025.1 or later and an internet connection.

## Commands

| Command | Action |
|---|---|
| NVDA+Alt+Shift+A | Turn the whole add-on on or off |
| NVDA+Alt+Shift+T | Turn translation on or off in the current conversation |
| NVDA+Alt+Shift+L | Choose the other party's language |
| NVDA+Alt+Shift+Enter | Send the message without translating it |
| NVDA+Alt+Shift+V | Paste the clipboard into the message field, translated |
| NVDA+Alt+Shift+O | Speak the original text of the last translation |
| NVDA+Alt+Shift+C | Translate the selected text or the clipboard; press twice to copy the translation |
| NVDA+Alt+Shift+H | History of translated messages |
| NVDA+Alt+Shift+S | Translation status |

The full guide to the add-on and its settings is in the [English guide](addon/doc/en/readme.html), also available from the installed add-ons in NVDA's Add-on Store.

## For developers

```
python -m unittest discover -s tests -t .
python build.py
```

The second command creates `chatTranslator-<version>.nvda-addon` in the repository folder, compiling the translation files on the way. Neither command needs NVDA or an internet connection.

To release: update the version in `addon/manifest.ini`, add the changes to `CHANGELOG.md`, then push a tag with the same number, such as `v1.2.0`. GitHub builds the add-on and publishes it on the releases page.

### Layout

- `addon/globalPlugins/chatTranslator/__init__.py`: the add-on itself: taking over Enter, filtering NVDA's speech, the commands.
- `addon/globalPlugins/chatTranslator/translators.py`: the translation services; does not depend on NVDA.
- `addon/globalPlugins/chatTranslator/settings.py`: the settings panel.
- `addon/globalPlugins/chatTranslator/languages.py`: the language list.
- `addon/globalPlugins/chatTranslator/detect.py`: recognising a text's language without going online; does not depend on NVDA.
- `addon/globalPlugins/chatTranslator/credentials.py`: storing the keys in Windows Credential Manager.
- `addon/locale/`: translations.
- `addon/doc/`: the user guide in Arabic and English.
- `tests/`: tests that run without NVDA.

## Translating into other languages

Translations into any language are welcome:

1. Run `python build.py pot` to create `chatTranslator.pot`.
2. Copy it to `addon/locale/<language code>/LC_MESSAGES/nvda.po`, for example `addon/locale/fr/LC_MESSAGES/nvda.po`, and fill in every `msgstr` line.
3. Translate the guide into `addon/doc/<language code>/readme.html` and the description into `addon/locale/<language code>/manifest.ini`.
4. Run the tests: they check that every string is translated and that markers such as `%s` match between the original and the translation.

## License

GNU General Public License, version 2 (GPL v2), the same license as NVDA. See [LICENSE](LICENSE).
