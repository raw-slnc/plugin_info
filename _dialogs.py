# -*- coding: utf-8 -*-
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QCoreApplication


class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
    """QTableWidgetItem that sorts by numeric UserRole value."""
    def __lt__(self, other):
        try:
            return float(self.data(Qt.UserRole)) < float(other.data(Qt.UserRole))
        except (ValueError, TypeError):
            return super().__lt__(other)


class PluginDetailDialog(QtWidgets.QDialog):
    """Dialog showing detailed information about a single plugin."""
    def __init__(self, plugin_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Plugin Details"))
        self.setMinimumSize(600, 400)

        layout = QtWidgets.QVBoxLayout(self)

        title_text = plugin_data.get('name', 'N/A')
        title = QtWidgets.QLabel(f"<h2>{title_text}</h2>")
        title.setWordWrap(True)
        layout.addWidget(title)

        author_line = self.tr("by {}").format(plugin_data.get('author_name', 'N/A'))
        layout.addWidget(QtWidgets.QLabel(author_line))

        description_browser = QtWidgets.QTextBrowser()
        description_browser.setOpenExternalLinks(True)
        description_browser.setHtml(plugin_data.get('description', 'No description available.'))
        layout.addWidget(description_browser)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def tr(self, message):
        return QCoreApplication.translate("PluginDetailDialog", message)
