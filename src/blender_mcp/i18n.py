"""Internationalization (i18n) support for Blender MCP (MP-06)."""

import json
import os
from pathlib import Path
from typing import Optional


class I18n:
    """Simple internationalization system.
    
    Supports English (en) and Portuguese (pt_BR).
    Falls back to English if translation not found.
    """
    
    SUPPORTED_LOCALES = ["en", "pt_BR"]
    DEFAULT_LOCALE = "en"
    
    def __init__(self, locale: Optional[str] = None):
        """Initialize i18n system.
        
        Args:
            locale: Locale to use (e.g., "en", "pt_BR"). 
                   If None, detects from environment.
        """
        self.current_locale = locale or self._detect_locale()
        self.translations = {}
        self._load_translations()
    
    def _detect_locale(self) -> str:
        """Detect locale from environment variables."""
        # Try environment variables in order
        for env_var in ["LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES"]:
            value = os.getenv(env_var, "")
            if value:
                # Extract locale code (e.g., "pt_BR.UTF-8" -> "pt_BR")
                locale_code = value.split(".")[0]
                
                # Map common variants
                if locale_code.startswith("pt"):
                    return "pt_BR"
                elif locale_code.startswith("en"):
                    return "en"
        
        return self.DEFAULT_LOCALE
    
    def _load_translations(self) -> None:
        """Load translation files for current locale and fallback."""
        translations_dir = Path(__file__).parent.parent.parent / "translations"
        
        # Always load English as fallback
        self.translations["en"] = self._load_json(translations_dir / "en.json")
        
        # Load current locale if different from English
        if self.current_locale != "en":
            locale_file = translations_dir / f"{self.current_locale}.json"
            if locale_file.exists():
                self.translations[self.current_locale] = self._load_json(locale_file)
            else:
                print(f"Warning: Translation file for '{self.current_locale}' not found, using English")
                self.current_locale = "en"
    
    def _load_json(self, filepath: Path) -> dict:
        """Load translation JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading translation file {filepath}: {e}")
            return {}
    
    def translate(self, key: str, **kwargs) -> str:
        """Translate a key to current locale.
        
        Args:
            key: Translation key
            **kwargs: Format parameters for the translation string
            
        Returns:
            Translated string with parameters formatted
        """
        # Try current locale
        if self.current_locale in self.translations:
            translation = self.translations[self.current_locale].get(key)
            if translation:
                return translation.format(**kwargs) if kwargs else translation
        
        # Fallback to English
        translation = self.translations.get("en", {}).get(key)
        if translation:
            return translation.format(**kwargs) if kwargs else translation
        
        # Return key if no translation found
        return key
    
    def set_locale(self, locale: str) -> None:
        """Change current locale.
        
        Args:
            locale: New locale code (e.g., "en", "pt_BR")
        """
        if locale not in self.SUPPORTED_LOCALES:
            print(f"Warning: Unsupported locale '{locale}', using '{self.DEFAULT_LOCALE}'")
            locale = self.DEFAULT_LOCALE
        
        self.current_locale = locale
        self._load_translations()
    
    def get_locale(self) -> str:
        """Get current locale."""
        return self.current_locale
    
    def get_supported_locales(self) -> list[str]:
        """Get list of supported locales."""
        return self.SUPPORTED_LOCALES.copy()


# Global i18n instance
_i18n_instance: Optional[I18n] = None


def get_i18n() -> I18n:
    """Get global i18n instance."""
    global _i18n_instance
    if _i18n_instance is None:
        _i18n_instance = I18n()
    return _i18n_instance


def _(key: str, **kwargs) -> str:
    """Shorthand for translating a key.
    
    Args:
        key: Translation key
        **kwargs: Format parameters
        
    Returns:
        Translated string
    """
    return get_i18n().translate(key, **kwargs)


def set_locale(locale: str) -> None:
    """Set application locale.
    
    Args:
        locale: Locale code (e.g., "en", "pt_BR")
    """
    get_i18n().set_locale(locale)


def get_locale() -> str:
    """Get current locale."""
    return get_i18n().get_locale()
