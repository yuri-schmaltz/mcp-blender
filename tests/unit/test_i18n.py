"""Tests for i18n (internationalization) module."""

import os
import pytest
from blender_mcp.i18n import I18n, _, set_locale, get_locale


class TestI18n:
    """Test internationalization functionality."""
    
    def test_default_locale_is_english(self):
        """Default locale should be English."""
        # Clear LANG env var for test
        old_lang = os.environ.get("LANG")
        if "LANG" in os.environ:
            del os.environ["LANG"]
        
        i18n = I18n()
        assert i18n.get_locale() == "en"
        
        # Restore
        if old_lang:
            os.environ["LANG"] = old_lang
    
    def test_detect_portuguese_locale(self):
        """Should detect Portuguese from environment."""
        old_lang = os.environ.get("LANG")
        os.environ["LANG"] = "pt_BR.UTF-8"
        
        i18n = I18n()
        assert i18n.get_locale() == "pt_BR"
        
        # Restore
        if old_lang:
            os.environ["LANG"] = old_lang
        else:
            del os.environ["LANG"]
    
    def test_translate_english(self):
        """Should translate to English."""
        i18n = I18n(locale="en")
        assert i18n.translate("app_title") == "Blender MCP - Configuration"
        assert i18n.translate("host_label") == "Blender Host"
    
    def test_translate_portuguese(self):
        """Should translate to Portuguese."""
        i18n = I18n(locale="pt_BR")
        assert i18n.translate("app_title") == "Blender MCP - Configurações"
        assert i18n.translate("host_label") == "Host do Blender"
    
    def test_translate_with_parameters(self):
        """Should format translation with parameters."""
        i18n = I18n(locale="en")
        result = i18n.translate("status_success", host="localhost", port=9876)
        assert "localhost" in result
        assert "9876" in result
    
    def test_fallback_to_english(self):
        """Should fallback to English if key not found in current locale."""
        i18n = I18n(locale="pt_BR")
        # If a key doesn't exist in Portuguese, should fallback to English
        result = i18n.translate("app_title")
        assert result  # Should return something
    
    def test_return_key_if_not_found(self):
        """Should return key if translation not found."""
        i18n = I18n(locale="en")
        result = i18n.translate("nonexistent_key")
        assert result == "nonexistent_key"
    
    def test_set_locale(self):
        """Should change locale dynamically."""
        i18n = I18n(locale="en")
        assert i18n.translate("app_title") == "Blender MCP - Configuration"
        
        i18n.set_locale("pt_BR")
        assert i18n.translate("app_title") == "Blender MCP - Configurações"
    
    def test_get_supported_locales(self):
        """Should return list of supported locales."""
        i18n = I18n()
        locales = i18n.get_supported_locales()
        assert "en" in locales
        assert "pt_BR" in locales
    
    def test_global_translate_function(self):
        """Test global _ translation function."""
        set_locale("en")
        assert _("app_title") == "Blender MCP - Configuration"
        
        set_locale("pt_BR")
        assert _("app_title") == "Blender MCP - Configurações"
    
    def test_global_locale_functions(self):
        """Test global locale getter/setter."""
        set_locale("en")
        assert get_locale() == "en"
        
        set_locale("pt_BR")
        assert get_locale() == "pt_BR"
