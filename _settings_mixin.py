# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings, QDate


class SettingsMixin:
    _SK_CREATED_SINCE_ENABLED = "PluginInfo/created_since_enabled"
    _SK_CREATED_SINCE_DATE = "PluginInfo/created_since_date"
    _SK_EXCLUDE_EXPERIMENTAL = "PluginInfo/exclude_experimental"
    _SK_EXCLUDE_DEPRECATED = "PluginInfo/exclude_deprecated"
    _SK_QGIS_MIN_LTR_ONLY = "PluginInfo/qgis_min_ltr_only"
    _SK_ONLY_EXPERIMENTAL = "PluginInfo/only_experimental"
    _SK_FAVORITES = "PluginInfo/favorites"

    def _restore_created_since_settings(self):
        settings = QSettings()
        enabled = settings.value(self._SK_CREATED_SINCE_ENABLED, False, type=bool)
        saved_date = settings.value(self._SK_CREATED_SINCE_DATE, "", type=str)
        restored = QDate.fromString(saved_date, "yyyy-MM-dd")
        if restored.isValid():
            self.created_since_date_edit.setDate(restored)
        self.created_since_checkbox.setChecked(bool(enabled))
        self.created_since_date_edit.setEnabled(bool(enabled))

    def _save_created_since_settings(self):
        settings = QSettings()
        settings.setValue(self._SK_CREATED_SINCE_ENABLED, self.created_since_checkbox.isChecked())
        settings.setValue(
            self._SK_CREATED_SINCE_DATE,
            self.created_since_date_edit.date().toString("yyyy-MM-dd"),
        )

    def _restore_filter_toggle_settings(self):
        settings = QSettings()
        self.exclude_experimental_button.setChecked(
            settings.value(self._SK_EXCLUDE_EXPERIMENTAL, False, type=bool)
        )
        self.exclude_deprecated_button.setChecked(
            settings.value(self._SK_EXCLUDE_DEPRECATED, False, type=bool)
        )
        self.qgis_min_ltr_button.setChecked(
            settings.value(self._SK_QGIS_MIN_LTR_ONLY, False, type=bool)
        )
        self.only_experimental_button.setChecked(
            settings.value(self._SK_ONLY_EXPERIMENTAL, False, type=bool)
        )

    def _save_filter_toggle_settings(self):
        settings = QSettings()
        settings.setValue(self._SK_EXCLUDE_EXPERIMENTAL, self.exclude_experimental_button.isChecked())
        settings.setValue(self._SK_EXCLUDE_DEPRECATED, self.exclude_deprecated_button.isChecked())
        settings.setValue(self._SK_QGIS_MIN_LTR_ONLY, self.qgis_min_ltr_button.isChecked())
        settings.setValue(self._SK_ONLY_EXPERIMENTAL, self.only_experimental_button.isChecked())

    def _load_favorites(self):
        settings = QSettings()
        favs = settings.value(self._SK_FAVORITES, [], type=list)
        self._favorites = set(str(f) for f in favs)

    def _save_favorites(self):
        settings = QSettings()
        settings.setValue(self._SK_FAVORITES, list(self._favorites))

    def _add_favorite(self, plugin_id):
        self._favorites.add(str(plugin_id))
        self._save_favorites()
        self.filter_table()

    def _remove_favorite(self, plugin_id):
        if str(plugin_id) in self._favorites:
            self._favorites.remove(str(plugin_id))
            self._save_favorites()
            self.filter_table()
