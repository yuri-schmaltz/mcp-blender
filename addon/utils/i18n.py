"""Internationalization (i18n) support for Blender Addon UI."""

import json
import os

# Shared instance
_i18n = None


class AddonI18n:
    def __init__(self):
        self.locale = self._detect_locale()
        self.translations = {}
        self._load_translations()

    def _detect_locale(self):
        """Detect locale from environment or system."""
        # Try Blender's internal locale if available (usually requires bpy)
        try:
            import bpy

            # Map Blender language to our codes
            b_lang = bpy.app.translations.locale
            if b_lang.startswith("pt"):
                return "pt_BR"
            if b_lang.startswith("en"):
                return "en"
        except ImportError:
            pass

        # Fallback to env vars
        for env_var in ["LANG", "LANGUAGE", "LC_ALL"]:
            val = os.getenv(env_var, "")
            if val.startswith("pt"):
                return "pt_BR"
            if val.startswith("en"):
                return "en"

        return "en"

    def _get_translations_path(self):
        """Find the translations directory, supporting both local dev and packaged extension."""
        # addon/utils/i18n.py -> addon/utils -> addon -> root (level 2)
        this_dir = os.path.dirname(os.path.abspath(__file__))

        # 1. Try local dev structure (translations at root)
        root_dev = os.path.dirname(os.path.dirname(this_dir))
        path_dev = os.path.join(root_dev, "translations")
        if os.path.exists(path_dev):
            return path_dev

        # 2. Try packaged structure (translations directly inside the zip/folder)
        # This usually means root_dev/translations as well, but sometimes bundled
        # alongside addon.py
        path_pkg = os.path.join(os.path.dirname(this_dir), "translations")
        if os.path.exists(path_pkg):
            return path_pkg

        # Fallback to current project root expectation
        return path_dev

    def _load_translations(self):
        """Load JSON files for current and default locales."""
        base_path = self._get_translations_path()

        # Always load English as fallback
        en_path = os.path.join(base_path, "en.json")
        self.translations["en"] = self._load_json(en_path)

        if self.locale != "en":
            loc_path = os.path.join(base_path, f"{self.locale}.json")
            if os.path.exists(loc_path):
                self.translations[self.locale] = self._load_json(loc_path)
            else:
                self.locale = "en"

    def _load_json(self, path):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def t(self, key, **kwargs):
        """Translate a key."""
        # Try current locale
        text = self.translations.get(self.locale, {}).get(key)
        if text is None:
            # Fallback to English
            text = self.translations.get("en", {}).get(key, key)

        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text


def t(key, **kwargs):
    global _i18n
    if _i18n is None:
        _i18n = AddonI18n()
    return _i18n.t(key, **kwargs)
