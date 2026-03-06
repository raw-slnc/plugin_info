# -*- coding: utf-8 -*-
import os
import configparser

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QDate
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsApplication, Qgis

from ._dialogs import NumericTableWidgetItem


class TableMixin:
    _QGIS_LTR_VERSIONS = {
        "2.18", "3.4", "3.10", "3.16", "3.22", "3.28", "3.34", "3.40",
    }

    def populate_table(self, plugins):
        """Populates the QTableWidget with the fetched plugin data."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(plugins))
        self._plugins_cache = list(plugins)
        installed_ids, installed_names = self._load_installed_plugin_index()

        self._refresh_filter_combos(plugins)

        for row, plugin in enumerate(plugins):
            downloads_value = int(plugin.get('downloads', 0) or 0)
            rating_value = float(plugin.get('rating', 0.0) or 0.0)
            version_value = str(plugin.get('version', 'N/A'))
            version_display = version_value if len(version_value) <= 8 else f"{version_value[:5]}..."

            name_item = QtWidgets.QTableWidgetItem(plugin['name'])
            name_item.setToolTip(plugin.get('description', ''))
            name_item.setData(Qt.UserRole, plugin['url'])
            name_item.setData(Qt.UserRole + 1, plugin['plugin_id'])
            name_item.setData(Qt.UserRole + 2, bool(plugin.get('experimental', False)))
            name_item.setData(Qt.UserRole + 3, bool(plugin.get('deprecated', False)))
            name_item.setData(Qt.UserRole + 4, plugin.get('create_date', QDate()))
            name_item.setData(Qt.UserRole + 5, str(plugin.get('qgis_minimum_version', '')).strip())
            name_item.setData(Qt.UserRole + 7, str(plugin.get('category', '')).strip())
            name_item.setData(self._ABOUT_DATA_ROLE, str(plugin.get('about', '') or ''))

            plugin_id_text = str(plugin.get('plugin_id', '') or '').strip().lower()
            plugin_name_text = str(plugin.get('name', '') or '').strip().lower()
            is_installed = (
                (plugin_id_text and plugin_id_text in installed_ids)
                or (plugin_name_text and plugin_name_text in installed_names)
            )
            name_item.setData(self._INSTALLED_DATA_ROLE, is_installed)

            supports_current = self._is_plugin_compatible_current_qgis(
                str(plugin.get('qgis_minimum_version', '')).strip(),
                str(plugin.get('qgis_maximum_version', '')).strip(),
            )
            name_item.setData(Qt.UserRole + 6, supports_current)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(plugin.get('plugin_id', 'N/A'))))

            version_item = QtWidgets.QTableWidgetItem(version_display)
            version_item.setToolTip(version_value)
            self.table.setItem(row, 2, version_item)

            downloads_item = NumericTableWidgetItem()
            downloads_item.setText(f"{downloads_value:,}")
            downloads_item.setData(Qt.UserRole, downloads_value)
            downloads_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, downloads_item)

            rating_item = NumericTableWidgetItem()
            stars_n = max(0, min(5, int(round(rating_value))))
            stars = ("★" * stars_n) + ("☆" * (5 - stars_n))
            rating_item.setText(f"{stars} ({rating_value:.1f})")
            rating_item.setData(Qt.UserRole, rating_value)
            rating_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, rating_item)

            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(plugin['author']))

            row_is_deprecated = bool(plugin.get('deprecated', False))
            row_is_experimental = bool(plugin.get('experimental', False))
            if row_is_deprecated:
                row_color = QColor(255, 240, 240)
            elif row_is_experimental:
                row_color = QColor(242, 250, 235)
            elif supports_current:
                row_color = QColor(238, 246, 255)
            else:
                row_color = QColor(255, 252, 232)

            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    item.setBackground(row_color)

            if is_installed:
                rating_cell = self.table.item(row, 4)
                if rating_cell is not None:
                    rating_cell.setForeground(QColor(255, 80, 40))
                    rating_cell.setToolTip(self.tr("Installed plugin"))

        self.table.setSortingEnabled(True)
        self.table.sortByColumn(3, Qt.DescendingOrder)
        self.filter_table()
        self._on_table_selection_changed()

    @staticmethod
    def _parse_metadata_file(path):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding='utf-8')
        if not parser.has_section('general'):
            return "", ""
        name = parser.get('general', 'name', fallback='').strip().lower()
        plugin_id = parser.get('general', 'plugin_id', fallback='').strip().lower()
        return plugin_id, name

    def _load_installed_plugin_index(self):
        installed_ids = set()
        installed_names = set()
        plugins_root = os.path.join(QgsApplication.qgisSettingsDirPath(), 'python', 'plugins')
        if not os.path.isdir(plugins_root):
            return installed_ids, installed_names

        for entry in os.listdir(plugins_root):
            meta_path = os.path.join(plugins_root, entry, 'metadata.txt')
            if not os.path.isfile(meta_path):
                continue
            try:
                plugin_id, name = self._parse_metadata_file(meta_path)
            except Exception:
                continue
            if plugin_id:
                installed_ids.add(plugin_id)
            if name:
                installed_names.add(name)
        return installed_ids, installed_names

    @staticmethod
    def _version_tuple(version_text):
        parts = []
        for token in str(version_text or "").split("."):
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits == "":
                break
            parts.append(int(digits))
        return tuple(parts)

    @classmethod
    def _is_ltr_version(cls, version_text):
        vt = cls._version_tuple(version_text)
        if len(vt) < 2:
            return False
        key = f"{vt[0]}.{vt[1]}"
        return key in cls._QGIS_LTR_VERSIONS

    def _is_plugin_compatible_current_qgis(self, min_version, max_version):
        current = self._version_tuple(getattr(Qgis, "QGIS_VERSION", ""))
        if not current:
            return True
        min_v = self._version_tuple(min_version)
        max_v = self._version_tuple(max_version)
        if min_v and current < min_v:
            return False
        if max_v and current > max_v:
            return False
        return True

    def _refresh_filter_combos(self, plugins):
        selected_minver = self.qgis_min_version_combo.currentData()
        selected_category = self.category_combo.currentData()

        exclude_experimental = self.exclude_experimental_button.isChecked()
        exclude_deprecated = self.exclude_deprecated_button.isChecked()
        only_experimental = self.only_experimental_button.isChecked()

        filtered_plugins = []
        for p in plugins:
            is_exp = p.get('experimental', False)
            is_dep = p.get('deprecated', False)
            if exclude_experimental and is_exp:
                continue
            if exclude_deprecated and is_dep:
                continue
            if only_experimental and not is_exp:
                continue
            filtered_plugins.append(p)

        min_versions = sorted(
            {str(p.get('qgis_minimum_version', '')).strip() for p in filtered_plugins
             if str(p.get('qgis_minimum_version', '')).strip()},
            key=self._version_tuple
        )
        if self.qgis_min_ltr_button.isChecked():
            min_versions = [v for v in min_versions if self._is_ltr_version(v)]

        categories = sorted(
            {str(p.get('category', '')).strip() for p in filtered_plugins
             if str(p.get('category', '')).strip() and str(p.get('category', '')).strip() != "N/A"}
        )
        if "Other" in categories:
            categories = [c for c in categories if c != "Other"] + ["Other"]

        self.qgis_min_version_combo.blockSignals(True)
        self.qgis_min_version_combo.clear()
        self.qgis_min_version_combo.addItem(self.tr("All QGIS min versions"), "")
        for v in min_versions:
            label = f"{v}-ltr" if self._is_ltr_version(v) else v
            self.qgis_min_version_combo.addItem(label, v)
        restore_idx = self.qgis_min_version_combo.findData(selected_minver)
        self.qgis_min_version_combo.setCurrentIndex(restore_idx if restore_idx >= 0 else 0)
        self.qgis_min_version_combo.blockSignals(False)

        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem(self.tr("All categories"), "")
        for c in categories:
            self.category_combo.addItem(c, c)
        restore_cat_idx = self.category_combo.findData(selected_category)
        self.category_combo.setCurrentIndex(restore_cat_idx if restore_cat_idx >= 0 else 0)
        self.category_combo.blockSignals(False)
