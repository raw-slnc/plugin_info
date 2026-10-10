# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QDate, Qt


class FilterMixin:

    def filter_table(self):
        """Hides or shows table rows based on active filter settings."""
        search_term = self.search_bar.text().lower()
        exclude_experimental = self.exclude_experimental_button.isChecked()
        exclude_deprecated = self.exclude_deprecated_button.isChecked()
        only_experimental = self.only_experimental_button.isChecked()
        selected_minver = str(self.qgis_min_version_combo.currentData() or "")
        selected_category = str(self.category_combo.currentData() or "")
        use_created_since = self.created_since_checkbox.isChecked()
        created_since_date = self.created_since_date_edit.date()
        show_favorites = self.show_favorites_button.isChecked()

        visible_rows = 0
        for i in range(self.table.rowCount()):
            name_text = self.table.item(i, 0).text().lower()
            plugin_id_text = self.table.item(i, 1).text().lower()
            version_text = self.table.item(i, 2).text().lower()
            author_text = self.table.item(i, 5).text().lower()
            is_experimental = bool(self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 2))
            is_deprecated = bool(self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 3))
            row_create_date = self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 4)
            row_minver = str(self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 5) or "")
            row_maxver = str(self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 10) or "")
            row_category = str(self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 7) or "")
            row_id = str(self.table.item(i, 0).data(Qt.ItemDataRole.UserRole + 1))

            match_text = (
                search_term in name_text
                or search_term in plugin_id_text
                or search_term in version_text
                or search_term in author_text
            )

            created_match = True
            if use_created_since:
                created_match = (
                    isinstance(row_create_date, QDate)
                    and row_create_date.isValid()
                    and row_create_date >= created_since_date
                )

            minver_match = (not selected_minver) or self._is_plugin_compatible_with_version(
                selected_minver,
                row_minver,
                row_maxver,
            )
            category_match = (not selected_category) or (row_category == selected_category)
            favorite_match = (not show_favorites) or (row_id in self._favorites)

            visible = (
                match_text
                and not (exclude_experimental and is_experimental)
                and not (exclude_deprecated and is_deprecated)
                and (not only_experimental or is_experimental)
                and created_match
                and minver_match
                and category_match
                and favorite_match
            )
            self.table.setRowHidden(i, not visible)
            if visible:
                visible_rows += 1

        self.status_label.setText(self.tr("{} plugins matching filter.").format(visible_rows))

    def _on_created_since_toggled(self, checked):
        self.created_since_date_edit.setEnabled(bool(checked))
        self._save_created_since_settings()
        self.filter_table()

    def _on_created_since_date_changed(self, _date):
        self._save_created_since_settings()
        self.filter_table()

    def _on_exclude_experimental_toggled(self, _checked):
        self._save_filter_toggle_settings()
        if self._plugins_cache:
            self._refresh_filter_combos(self._plugins_cache)
        self.filter_table()

    def _on_exclude_deprecated_toggled(self, _checked):
        self._save_filter_toggle_settings()
        if self._plugins_cache:
            self._refresh_filter_combos(self._plugins_cache)
        self.filter_table()

    def _on_qgis_min_ltr_toggled(self, _checked):
        self._save_filter_toggle_settings()
        if self._plugins_cache:
            self._refresh_filter_combos(self._plugins_cache)
        self.filter_table()

    def _on_only_experimental_toggled(self, _checked):
        self._save_filter_toggle_settings()
        if self._plugins_cache:
            self._refresh_filter_combos(self._plugins_cache)
        self.filter_table()

    def _on_show_favorites_toggled(self, checked):
        self.filter_table()
