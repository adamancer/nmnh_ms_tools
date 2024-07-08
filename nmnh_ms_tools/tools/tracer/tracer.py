import base64
import json
import os
import sys

from PySide2.QtCore import Qt, QPoint, QRect
from PySide2.QtGui import (
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PySide2.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QWidget,
)
import rasterio
from shapely.geometry import Polygon


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle("tracer")
        self.setGeometry(0, 0, 1280, 960)
        self.setMouseTracking(True)

        self.stack = QStackedWidget(self)
        self.widgets = [
            QRefPoint(self, "Select reference points", show_polygon=False),
            QTracer(self, "Draw polygon", show_crosshair=False),
        ]
        for widget in self.widgets:
            self.stack.addWidget(widget)
        self.setCentralWidget(self.stack)

        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)

        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        self.path = None
        self.imgdata = None
        self.pixmap = None

        # Add open button to toolbar
        button = QAction(QIcon("icons/folder-open.png"), "Open file", self)
        button.setStatusTip("This is your button")
        button.triggered.connect(self.open_file)
        self.toolbar.addAction(button)

        # Add save button to toolbar
        button = QAction(QIcon("icons/document-export.png"), "Export", self)
        button.setStatusTip("This is your button")
        button.triggered.connect(self.export)
        self.toolbar.addAction(button)

        # Add layer switch to toolbar
        button = QAction(QIcon("icons/layers-arrange.png"), "Change layer", self)
        button.setStatusTip("This is your button")
        button.triggered.connect(self.change_layer)
        self.toolbar.addAction(button)

        # Add layer switch to toolbar
        button = QAction(QIcon("icons/minus-circle.png"), "Clear points", self)
        button.setStatusTip("This is your button")
        button.triggered.connect(self.clear_points)
        self.toolbar.addAction(button)

        # Add transform button
        button = QAction(QIcon("icons/layer-shape-polygon.png"), "Polygon", self)
        button.setStatusTip("This is your button")
        button.triggered.connect(self.transform)
        self.toolbar.addAction(button)

    def open_file(self):
        types = "Image files (*.jpg *.png);;JSON files (*.json)"
        path = QFileDialog().getOpenFileName(self, "Open file", ".", types)[0]
        if os.path.splitext(path)[-1].lower() == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Write image to temporary file
            self.path = data["path"]
            self.imgdata = base64.b64decode(data["imgdata"])

            for widget in self.widgets:
                anchors = data.get(widget.title, [])
                widget.anchors = [QAnchor(widget, *a) for a in anchors]
                widget.update()

        elif path:
            self.path = path
            with open(path, "rb") as f:
                self.imgdata = f.read()
            for widget in self.widgets:
                widget.anchors = []
                widget.update()

        # Read pixel map from image data
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(
            self.imgdata, os.path.splitext(self.path)[-1].rstrip(".").upper()
        )

    def export(self):
        data = {
            "path": self.path,
            "imgdata": base64.b64encode(self.imgdata).decode("utf-8"),
        }

        for widget in self.widgets:
            data[widget.title] = [[a.x, a.y, a.label] for a in widget.anchors]

        types = "JSON files (*.json)"
        path = QFileDialog().getSaveFileName(self, "Save file", ".", types)[0]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def change_layer(self):
        self.stack.setCurrentIndex(0 if self.stack.currentIndex() else 1)

    def clear_points(self):
        widget = self.stack.currentWidget()
        widget.anchors = []
        widget.update()

    def transform(self):

        gcps = []
        for anchor in self.widgets[0].anchors:
            col, row = anchor.widget.get_orig_coords(anchor.x, anchor.y)
            y, x = anchor.lat_lng()
            gcps.append(rasterio.control.GroundControlPoint(row, col, x, y))
        transform = rasterio.transform.from_gcps(gcps)

        rows = []
        cols = []
        for anchor in self.widgets[1].anchors:
            col, row = anchor.widget.get_orig_coords(anchor.x, anchor.y)
            rows.append(row)
            cols.append(col)
        result = rasterio.transform.xy(transform, rows, cols)

        print(Polygon(zip(*result)))


class QTracer(QWidget):

    def __init__(
        self, window, title, show_polygon=True, show_points=True, show_crosshair=True
    ):
        super().__init__()
        self.window = window
        self.title = title
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)

        self.position = None
        self.anchors = []
        self.anchor = None
        self.mousedown = None

        self.show_polygon = show_polygon
        self.show_points = show_points
        self.show_crosshair = show_crosshair

    def keyPressEvent(self, event):
        if self.anchor:
            if event.key() == Qt.Key_Up:
                self.anchor.y -= 1 / self.height()
            elif event.key() == Qt.Key_Right:
                self.anchor.x += 1 / self.width()
            elif event.key() == Qt.Key_Down:
                self.anchor.y += 1 / self.height()
            elif event.key() == Qt.Key_Left:
                self.anchor.x -= 1 / self.width()
            self.position = self.get_abs_coords(self.anchor.x, self.anchor.y)
            self.update()

    def mouseMoveEvent(self, event):
        self.position = (event.x(), event.y())
        x, y = self.get_rel_coords(event.x(), event.y())
        self.window.statusbar.showMessage(f"x={x}, y={y}", 10000)
        if self.mousedown and self.anchor:
            self.anchor.drag(event.x(), event.y())
            # self.update()
        else:
            hover = [a.hover for a in self.anchors]
            for anchor in self.anchors:
                anchor.hover = anchor.rect().contains(event.x(), event.y())
            # if hover != [a.hover for a in self.anchors]:
            #    self.update()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.handle_left_click(event)
        elif event.button() == Qt.RightButton:
            self.handle_right_click(event)

    def mouseReleaseEvent(self, event):
        self.mousedown = None

    def paintEvent(self, event):
        if self.window.imgdata:

            painter = QPainter(self)

            pixmap = self.window.pixmap
            pixmap.scaled(self.size())
            painter.drawPixmap(0, 0, self.width(), self.height(), pixmap)

            # Draw crosshair
            if self.show_crosshair and self.position:
                x, y = self.position
                painter.setPen(QPen(Qt.black, 1, Qt.SolidLine))
                painter.drawLine(x, 0, x, self.height())
                painter.drawLine(0, y, self.width(), y)

            if self.anchors:
                points = []
                for anchor in self.anchors:
                    points.append(anchor.point())

                    if self.show_points:
                        color = Qt.red if anchor.highlight() else Qt.blue
                        painter.setPen(QPen(color, 4, Qt.SolidLine))
                        painter.drawRect(anchor.rect())

                        # Draw the anchor label if exists
                        if anchor.label:
                            painter.setFont(QFont("Arial", 12))
                            x, y = self.get_abs_coords(anchor.x, anchor.y)
                            painter.drawText(x, y - anchor.dim, anchor.label)

                if self.show_polygon:
                    painter.setPen(QPen(Qt.blue, 4, Qt.SolidLine))
                    painter.drawPolygon(QPolygon(points))

            painter.end()

    def handle_left_click(self, event):
        self.mousedown = (event.x(), event.y())
        for anchor in self.anchors:
            if anchor.mouseover(event.x(), event.y()):
                self.deactivate_anchors()
                anchor.active = True
                self.anchor = anchor
                break
        else:
            i = 0
            if self.anchors:
                i = [i for i, a in enumerate(self.anchors) if a.active][0]
            self.deactivate_anchors()
            anchor = QAnchor(self, event.x(), event.y())
            self.anchors.insert(i + 1, anchor)
            self.anchor = anchor
            self.update()

    def handle_right_click(self, event):
        anchors = []
        for i, anchor in enumerate(self.anchors):
            if anchor.mouseover(event.x(), event.y()):
                if anchors:
                    self.anchors[i - 1].active = True
                elif len(self.anchors) > 1:
                    self.anchors[i + 1].active = True
            else:
                anchors.append(anchor)
        self.anchors = anchors
        self.update()

    def deactivate_anchors(self):
        for anchor in self.anchors:
            anchor.active = False

    def export(self):
        return [self.x, self.y, self.label]

    def get_rel_coords(self, x, y):
        return x / self.width(), y / self.height()

    def get_abs_coords(self, x, y):
        return x * self.width(), y * self.height()

    def get_orig_coords(self, x, y):
        height = self.window.pixmap.size().height()
        return x * self.window.pixmap.size().width(), height * (1 - y)


class QRefPoint(QTracer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.anchor and not self.anchor.label:
            self.anchor.set_label()

    def mouseDoubleClickEvent(self, event):
        if self.anchor:
            self.anchor.set_label()


class QAnchor:

    def __init__(self, widget, x, y, label=None):
        self.widget = widget
        self.x = x if isinstance(x, float) else x / self.widget.width()
        self.y = y if isinstance(y, float) else y / self.widget.height()
        self.label = label
        self.dim = 16
        self.active = True
        self.hover = False

    def lat_lng(self):
        lat, lng = [float(c.strip()) for c in self.label.split(",")]
        return lat, lng

    def point(self):
        return QPoint(*self.widget.get_abs_coords(self.x, self.y))

    def rect(self):
        x, y = self.widget.get_abs_coords(self.x, self.y)
        return QRect(x - self.dim / 2, y - self.dim / 2, self.dim, self.dim)

    def highlight(self):
        return self.active or self.hover

    def mouseover(self, x, y):
        return self.rect().contains(x, y)

    def drag(self, x, y):
        self.x = x / self.widget.width()
        self.y = y / self.widget.height()

    def set_label(self):
        try:
            lat, lng = self.lat_lng()
        except (AttributeError, ValueError):
            lat = 0
            lng = 0

        lat = QInputDialog.getDouble(
            self.widget,
            "Set latitude",
            "Latitude",
            lat,
            minValue=-90,
            maxValue=90,
            decimals=3,
        )
        lng = QInputDialog.getDouble(
            self.widget,
            "Set longitude",
            "Longitude",
            lng,
            minValue=-180,
            maxValue=180,
            decimals=3,
        )

        self.label = f"{lat[0]:.3f}, {lng[0]:.3f}"


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec_()
