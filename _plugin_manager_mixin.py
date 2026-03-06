# -*- coding: utf-8 -*-
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QGuiApplication


class PluginManagerMixin:

    def open_plugin_url(self, item):
        """Opens the plugin homepage in the default browser."""
        name_item = self.table.item(item.row(), 0)
        url = name_item.data(Qt.UserRole)
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            self.status_label.setText(self.tr("No homepage URL available for this plugin."))

    def open_plugin_manager_for_item(self, item):
        """Open Plugin Manager and copy plugin name to clipboard."""
        if self.iface is None:
            self.status_label.setText(self.tr("QGIS interface is not available."))
            return

        name_item = self.table.item(item.row(), 0)
        plugin_name = name_item.text().strip() if name_item is not None else ""

        # Copy plugin name to clipboard
        if plugin_name:
            QGuiApplication.clipboard().setText(plugin_name)

        # Open plugin manager
        opened = self._open_qgis_plugin_manager()
        if opened:
            if plugin_name:
                self.status_label.setText(
                    self.tr('Opened Plugin Manager. "{}" copied to clipboard — paste in search.').format(plugin_name)
                )
            else:
                self.status_label.setText(self.tr("Opened Plugin Manager."))
        else:
            self.status_label.setText(
                self.tr("Plugin manager API/action is not available in this QGIS build.")
            )

    def _open_qgis_plugin_manager(self):
        # 1) Try iface methods first.
        for method_name in ("showPluginManager", "openPluginManager", "showPluginManagerDialog"):
            method = getattr(self.iface, method_name, None)
            if not callable(method):
                continue
            try:
                method()
                return True
            except Exception:
                pass

        # 2) Fallback: trigger known main-window actions.
        mw = self.iface.mainWindow() if hasattr(self.iface, "mainWindow") else None
        if mw is None:
            return False

        for obj_name in ("mActionShowPluginManager", "mActionManagePlugins"):
            action = mw.findChild(QtWidgets.QAction, obj_name)
            if action is not None:
                action.trigger()
                return True

        # 3) Last resort: find by action text.
        for action in mw.findChildren(QtWidgets.QAction):
            text = (action.text() or "").lower()
            if "manage and install" in text and "plugin" in text:
                action.trigger()
                return True
            if ("plugin" in text and "manage" in text) or ("プラグイン" in text and "管理" in text):
                action.trigger()
                return True

        return False

    def show_table_context_menu(self, pos):
        """Shows a context menu on right-click."""
        if not self.table.selectionModel().hasSelection():
            return

        menu = QtWidgets.QMenu()
        selected_items = self.table.selectedItems()
        name_item = self.table.item(selected_items[0].row(), 0)
        plugin_id = str(name_item.data(Qt.UserRole + 1))

        if plugin_id in self._favorites:
            action = menu.addAction(self.tr("Remove from Favorites"))
            action.triggered.connect(lambda: self._remove_favorite(plugin_id))
        else:
            action = menu.addAction(self.tr("Add to Favorites"))
            action.triggered.connect(lambda: self._add_favorite(plugin_id))

        menu.exec_(self.table.mapToGlobal(pos))
