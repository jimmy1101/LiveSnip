import json
import urllib.request
import urllib.parse
from typing import Tuple, Dict, Optional
from PySide6.QtCore import QThread, Signal

# Language code to display name mapping
LANGUAGE_MAP: Dict[str, str] = {
    "zh-CN": "🇨🇳 简体中文",
    "en": "🇺🇸 英语",
    "ja": "🇯🇵 日语",
    "ko": "🇰🇷 韩语",
    "ru": "🇷🇺 俄语",
    "fr": "🇫🇷 法语",
    "de": "🇩🇪 德语",
    "es": "🇪🇸 西班牙语",
    "zh-TW": "🇭🇰 繁体中文",
}

LANGUAGE_NAMES: Dict[str, str] = {
    "zh-CN": "简体中文",
    "zh": "中文",
    "zh-TW": "繁体中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "ru": "俄语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "vi": "越南语",
    "th": "泰语",
    "ar": "阿拉伯语",
}

def get_language_display_name(code: str) -> str:
    """Return friendly name for a language code."""
    code_lower = code.lower().replace("_", "-")
    for k, v in LANGUAGE_NAMES.items():
        if k.lower() == code_lower or code_lower.startswith(k.lower()):
            return v
    return code.upper()

def detect_local_language(text: str) -> str:
    """Fast local heuristic detection based on Unicode character scripts."""
    if not text:
        return "en"

    cjk = 0
    kana = 0
    hangul = 0
    cyrillic = 0
    latin = 0

    for ch in text:
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF:
            kana += 1
        elif (0xAC00 <= code <= 0xD7AF) or (0x1100 <= code <= 0x11FF):
            hangul += 1
        elif 0x0400 <= code <= 0x04FF:
            cyrillic += 1
        elif (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF):
            cjk += 1
        elif ('a' <= ch <= 'z') or ('A' <= ch <= 'Z'):
            latin += 1

    if kana > 0:
        return "ja"
    if hangul > 0:
        return "ko"
    if cyrillic > 0:
        return "ru"
    if cjk > 0:
        return "zh-CN"
    return "en"

def get_auto_target_lang(source_lang: str) -> str:
    """Decide smart target language: if source is Chinese, target is English; else target is Chinese."""
    if source_lang.lower().startswith("zh"):
        return "en"
    return "zh-CN"

def _translate_via_google(text: str, target_lang: str, source_lang: str = "auto", timeout: int = 8) -> Tuple[str, str]:
    """Primary translation provider via Google Translate."""
    q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={source_lang}&tl={target_lang}&dt=t&q={q}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        detected_src = data[2] if len(data) > 2 and data[2] else source_lang
        parts = []
        if data and data[0]:
            for item in data[0]:
                if item and item[0]:
                    parts.append(item[0])
        translated = "".join(parts)
        return translated, detected_src

def _translate_via_mymemory(text: str, target_lang: str, source_lang: str = "auto", timeout: int = 8) -> Tuple[str, str]:
    """Fallback translation provider via MyMemory."""
    src = source_lang if source_lang != "auto" else detect_local_language(text)
    tgt = target_lang
    q = urllib.parse.quote(text)
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair={src}|{tgt}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        translated = data.get("responseData", {}).get("translatedText", "")
        return translated, src

def translate_text(text: str, target_lang: str = "auto", source_lang: str = "auto") -> Tuple[str, str, str]:
    """
    Translate given text with automatic language detection.
    Returns: (translated_text, detected_source_lang, target_lang)
    """
    clean_text = text.strip()
    if not clean_text:
        return "", "auto", "zh-CN"

    # Auto target determination
    if target_lang == "auto":
        local_src = detect_local_language(clean_text)
        actual_target = get_auto_target_lang(local_src)
    else:
        actual_target = target_lang

    # 1. Try Google primary engine
    try:
        translated, detected_src = _translate_via_google(clean_text, actual_target, source_lang)
        if target_lang == "auto":
            # If Google detected a different source language that changes our decision
            correct_tgt = get_auto_target_lang(detected_src)
            if correct_tgt != actual_target:
                translated, detected_src = _translate_via_google(clean_text, correct_tgt, detected_src)
                actual_target = correct_tgt
        return translated, detected_src, actual_target
    except Exception as e_google:
        print(f"[Translator] Google provider failed: {e_google}, falling back to MyMemory...")

    # 2. Try MyMemory fallback engine
    try:
        translated, detected_src = _translate_via_mymemory(clean_text, actual_target, source_lang)
        return translated, detected_src, actual_target
    except Exception as e_mymemory:
        raise RuntimeError(f"翻译服务连接异常: {e_google}; 备用源异常: {e_mymemory}")

class TranslationWorker(QThread):
    finished_translation = Signal(dict)

    def __init__(self, text: str, target_lang: str = "auto", source_lang: str = "auto", parent=None):
        super().__init__(parent)
        self.text = text.strip()
        self.target_lang = target_lang
        self.source_lang = source_lang

    def run(self):
        if not self.text:
            self.finished_translation.emit({
                "original": "",
                "translated": "",
                "source_lang": "auto",
                "target_lang": "zh-CN",
                "success": False,
                "error": "待翻译文本为空"
            })
            return

        try:
            translated, src_lang, tgt_lang = translate_text(self.text, self.target_lang, self.source_lang)
            self.finished_translation.emit({
                "original": self.text,
                "translated": translated,
                "source_lang": src_lang,
                "target_lang": tgt_lang,
                "success": True,
                "error": ""
            })
        except Exception as e:
            self.finished_translation.emit({
                "original": self.text,
                "translated": "",
                "source_lang": self.source_lang,
                "target_lang": self.target_lang,
                "success": False,
                "error": str(e)
            })
