# -*- coding: utf-8 -*-
import json
import xml.etree.ElementTree as ET

from qgis.PyQt.QtCore import QUrl, QDate, Qt
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsNetworkAccessManager, Qgis, QgsMessageLog

from ._dialogs import PluginDetailDialog


class NetworkMixin:
    PLUGIN_REPOSITORY_URL_TEMPLATE = "https://plugins.qgis.org/plugins/plugins.xml?qgis={qgis_version}"
    PLUGIN_REPOSITORY_URL_FALLBACK = "https://plugins.qgis.org/plugins/plugins.xml"

    def fetch_plugins(self):
        """Fetch plugin list from repository URLs (with fallbacks)."""
        self.status_label.setText(self.tr("Fetching plugin list from repository..."))
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._repo_try_index = 0
        self._start_plugins_request()

    def _start_plugins_request(self):
        if self._plugins_reply is not None:
            self._plugins_reply.abort()
            self._plugins_reply.deleteLater()
            self._plugins_reply = None

        if self._repo_try_index >= len(self._repo_urls):
            self.progress_bar.setVisible(False)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.populate_table([])
            self._update_debug_headers([])
            self.status_label.setText(self.tr("No plugins returned from repository."))
            QgsMessageLog.logMessage(
                f"No plugins returned. URLs tried: {', '.join(self._repo_urls)}",
                'Plugin Info Browser',
                Qgis.Warning
            )
            return

        repo_url = self._repo_urls[self._repo_try_index]
        self._pending_mode = "plugins"
        self.status_label.setText(
            self.tr("Fetching plugin list from repository... ({}/{})").format(
                self._repo_try_index + 1,
                len(self._repo_urls)
            )
        )

        request = QNetworkRequest(QUrl(repo_url))
        request.setRawHeader(b"User-Agent", b"QGIS-Plugin-Browser")
        self._plugins_reply = QgsNetworkAccessManager.instance().get(request)
        self._plugins_reply.downloadProgress.connect(self._on_network_progress)
        self._plugins_reply.finished.connect(self._on_plugins_reply_finished)
        self._network_timeout.start(20000)

    def _on_plugins_reply_finished(self):
        self._network_timeout.stop()
        reply = self._plugins_reply
        self._plugins_reply = None
        self._pending_mode = None

        if reply is None:
            return

        current_url = self._repo_urls[self._repo_try_index]
        err = reply.error()
        if err != 0:
            QgsMessageLog.logMessage(
                f"Repository request failed: {reply.errorString()} (url: {current_url})",
                'Plugin Info Browser',
                Qgis.Warning
            )
            reply.deleteLater()
            self._repo_try_index += 1
            self._start_plugins_request()
            return

        try:
            plugins, headers = self._parse_plugins_xml(bytes(reply.readAll()))
        except Exception as ex:
            QgsMessageLog.logMessage(
                f"XML parse failed: {ex} (url: {current_url})",
                'Plugin Info Browser',
                Qgis.Warning
            )
            reply.deleteLater()
            self._repo_try_index += 1
            self._start_plugins_request()
            return

        reply.deleteLater()
        if not plugins:
            self._repo_try_index += 1
            self._start_plugins_request()
            return

        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.populate_table(plugins)
        self._update_debug_headers(headers)
        self.status_label.setText(self.tr("{} plugins found.").format(len(plugins)))

    def _update_debug_headers(self, headers):
        """Populates the two-column debug header view."""
        sorted_headers = sorted(list(headers))
        self.debug_headers_label_left.setText("")
        self.debug_headers_label_right.setText("")
        if not sorted_headers:
            return
        split_point = (len(sorted_headers) + 1) // 2
        self.debug_headers_label_left.setText("\n".join(sorted_headers[:split_point]))
        self.debug_headers_label_right.setText("\n".join(sorted_headers[split_point:]))

    @staticmethod
    def _parse_plugins_xml(xml_data):
        root = ET.fromstring(xml_data)
        all_plugins = [
            elem for elem in root.iter()
            if elem.tag == 'pyqgis_plugin' or str(elem.tag).endswith('}pyqgis_plugin')
        ]
        header_names = set()

        def findtext_local(elem, local_name, default=''):
            for child in list(elem):
                tag = str(child.tag)
                if tag == local_name or tag.endswith('}' + local_name):
                    return child.text or default
            return default

        def parse_bool(value):
            text = str(value).strip().lower()
            return text in ('1', 'true', 'yes', 'y', 'on')

        def normalize_category(category_text, tags_text):
            raw = " ".join([
                str(category_text or "").strip().lower(),
                str(tags_text or "").strip().lower(),
            ])
            if not raw:
                return "Other"
            if any(k in raw for k in ("process", "processing", "algorithm", "model builder", "geoprocess")):
                return "Processing"
            if any(k in raw for k in ("vector", "shp", "shapefile", "geojson", "feature", "geometry")):
                return "Vector"
            if any(k in raw for k in ("raster", "dem", "tif", "tiff", "imagery", "satellite", "elevation")):
                return "Raster"
            if any(k in raw for k in ("database", "postgis", "spatialite", "sql", "db")):
                return "Database"
            if any(k in raw for k in ("web", "wms", "wfs", "wmts", "tile", "xyz", "basemap", "mapbox")):
                return "Web"
            if any(k in raw for k in ("3d", "mesh", "point cloud", "pointcloud")):
                return "3D"
            if any(k in raw for k in ("layout", "print", "atlas", "report")):
                return "Layout"
            if any(k in raw for k in ("gps", "track", "gnss")):
                return "GPS"
            return "Other"

        parsed = []
        for plugin_elem in all_plugins:
            for attr_name in plugin_elem.attrib.keys():
                header_names.add(attr_name)
            for child in list(plugin_elem):
                tag = str(child.tag)
                if "}" in tag:
                    tag = tag.split("}", 1)[1]
                header_names.add(tag)

            downloads_value = findtext_local(plugin_elem, 'downloads', '0') or '0'
            rating_value = findtext_local(plugin_elem, 'average_vote', '0.0') or '0.0'
            tags_value = findtext_local(plugin_elem, 'tags', '')
            experimental_value = findtext_local(plugin_elem, 'experimental', 'False')
            deprecated_value = findtext_local(plugin_elem, 'deprecated', 'False')
            create_date_value = findtext_local(plugin_elem, 'create_date', '')
            description_value = findtext_local(plugin_elem, 'description', '')
            about_value = findtext_local(plugin_elem, 'about', '')
            raw_category = (
                findtext_local(plugin_elem, 'category', '')
                or plugin_elem.get('category', '')
            )
            category_value = normalize_category(raw_category, tags_value)
            create_date_qdate = QDate.fromString(create_date_value[:10], "yyyy-MM-dd")
            if not create_date_qdate.isValid():
                create_date_qdate = QDate()
            parsed.append({
                'id': plugin_elem.get('id'),
                'plugin_id': plugin_elem.get('plugin_id') or plugin_elem.get('id') or 'N/A',
                'version': plugin_elem.get('version') or findtext_local(plugin_elem, 'version', 'N/A'),
                'name': plugin_elem.get('name', 'N/A'),
                'description': description_value,
                'about': about_value,
                'category': category_value,
                'downloads': int(downloads_value),
                'rating': float(rating_value),
                'experimental': parse_bool(experimental_value),
                'deprecated': parse_bool(deprecated_value),
                'create_date': create_date_qdate,
                'qgis_minimum_version': findtext_local(plugin_elem, 'qgis_minimum_version', ''),
                'qgis_maximum_version': findtext_local(plugin_elem, 'qgis_maximum_version', ''),
                'author': findtext_local(plugin_elem, 'author_name', 'N/A'),
                'url': findtext_local(plugin_elem, 'homepage', '')
            })
        return parsed, sorted(header_names)

    @classmethod
    def _build_repository_urls(cls):
        """Build repository URL candidates for compatibility across server behaviors."""
        ver = getattr(Qgis, "QGIS_VERSION", "3.0")
        numeric = []
        for part in ver.split("."):
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits == "":
                break
            numeric.append(digits)
            if len(numeric) == 3:
                break

        variants = []
        if len(numeric) >= 2:
            variants.append(".".join(numeric[:2]))
        if len(numeric) >= 1:
            variants.append(numeric[0])

        urls = [
            cls.PLUGIN_REPOSITORY_URL_TEMPLATE.format(qgis_version=v)
            for v in variants
        ]
        urls.append(cls.PLUGIN_REPOSITORY_URL_FALLBACK)

        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    def show_plugin_details(self):
        """Fetches and displays the details for the selected plugin."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        name_item = self.table.item(selected_items[0].row(), 0)
        plugin_id = name_item.data(Qt.UserRole + 1)

        if not plugin_id:
            self.status_label.setText(self.tr("Could not find plugin ID."))
            return

        self.status_label.setText(self.tr("Fetching details for plugin {}...").format(plugin_id))
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._pending_mode = "details"
        self._details_plugin_id = plugin_id

        if self._details_reply is not None:
            self._details_reply.abort()
            self._details_reply.deleteLater()
            self._details_reply = None

        request = QNetworkRequest(QUrl(f"https://plugins.qgis.org/api/plugins/{plugin_id}/"))
        request.setRawHeader(b"User-Agent", b"QGIS-Plugin-Browser")
        self._details_reply = QgsNetworkAccessManager.instance().get(request)
        self._details_reply.downloadProgress.connect(self._on_network_progress)
        self._details_reply.finished.connect(self._on_details_reply_finished)
        self._network_timeout.start(15000)

    def _on_details_reply_finished(self):
        self._network_timeout.stop()
        reply = self._details_reply
        self._details_reply = None
        self._pending_mode = None
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        if reply is None:
            return

        err = reply.error()
        if err != 0:
            error_msg = self.tr("Error fetching details: {}").format(reply.errorString())
            self.status_label.setText(error_msg)
            QgsMessageLog.logMessage(error_msg, 'Plugin Info Browser', Qgis.Critical)
            reply.deleteLater()
            return

        try:
            result = json.loads(bytes(reply.readAll()).decode("utf-8", errors="replace"))
        except Exception as ex:
            self.status_label.setText(self.tr("Error parsing details JSON: {}").format(ex))
            QgsMessageLog.logMessage(str(ex), 'Plugin Info Browser', Qgis.Critical)
            reply.deleteLater()
            return

        reply.deleteLater()
        if not result:
            self.status_label.setText(self.tr("No detail data was returned."))
            return

        self.status_label.setText(self.tr("Details loaded."))
        detail_dialog = PluginDetailDialog(result, self)
        detail_dialog.exec_()

    def _on_network_progress(self, received, total):
        if total and total > 0:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int((received * 100) / total))
        else:
            if self.progress_bar.maximum() != 0:
                self.progress_bar.setRange(0, 0)

    def _on_network_timeout(self):
        if self._pending_mode == "plugins" and self._plugins_reply is not None:
            self._plugins_reply.abort()
            return
        if self._pending_mode == "details" and self._details_reply is not None:
            self._details_reply.abort()
            return
