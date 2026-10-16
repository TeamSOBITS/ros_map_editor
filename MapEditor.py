from PyQt5 import QtCore, QtGui, QtWidgets, uic

from ui_map_editor import Ui_MapEditor

from PyQt5.QtGui import QPainter, QBrush, QPen
from PyQt5.QtCore import Qt

import math
import yaml
from PIL import Image
import sys
import os


class MapEditor(QtWidgets.QMainWindow):
    def __init__(self, fn):
        super(MapEditor, self).__init__()

        # two approaches to integrating tool generated ui file shown below
        
        # setup user interface directly from ui file
        #uic.loadUi('UI_MapEditor.ui', self)

        # setup user interface from py module converted from ui file
        self.ui = Ui_MapEditor()
        self.ui.setupUi(self)

        self.setMinimumSize(600, 600)

        self.ui.zoomBox.addItem("100 %", 1)
        self.ui.zoomBox.addItem("200 %", 2)
        self.ui.zoomBox.addItem("400 %", 4)
        self.ui.zoomBox.addItem("800 %", 8)
        self.ui.zoomBox.addItem("1600 %", 16)
        self.ui.zoomBox.currentIndexChanged.connect(self.handleZoom)

        self.ui.colorBox.addItem('alternate', 0)
        self.ui.colorBox.addItem('occupied', 1)
        self.ui.colorBox.addItem('unoccupied', 2)
        self.ui.colorBox.addItem('uncertain', 3)
        self.ui.colorBox.currentIndexChanged.connect(self.handleColor)
        self.color = 'alternate'

        self.ui.rectSelectCheckBox.stateChanged.connect(self.handleRectMode)
        self.rect_select_mode = False
        self.rect_start = None
        self.rect_preview_item = None

        self.read(fn)

        view_width = self.frameGeometry().width()

        self.min_multiplier = math.ceil(view_width / self.map_width_cells)
        self.zoom = 1
        self.pixels_per_cell = self.min_multiplier * self.zoom 

        self.draw_map()
        
        self.ui.closeButton.clicked.connect(self.closeEvent)
        self.ui.saveButton.clicked.connect(self.saveEvent)

        self.ui.graphicsView.horizontalScrollBar().valueChanged.connect(self.scrollChanged)
        self.ui.graphicsView.verticalScrollBar().valueChanged.connect(self.scrollChanged)

        self.ui.graphicsView.setMouseTracking(True)
        self.ui.graphicsView.viewport().installEventFilter(self)


    def eventFilter(self, source, event):
        if source is self.ui.graphicsView.viewport():
            rect_active = self.rect_select_mode and self.color != 'alternate'

            if rect_active and event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                x, y = self.clamp_cell(*self.view_pos_to_cell(event.pos()))
                self.rect_start = (x, y)
                self.update_rect_preview(x, y)

            elif rect_active and self.rect_start is not None and event.type() == QtCore.QEvent.MouseMove and event.buttons() == QtCore.Qt.LeftButton:
                x, y = self.clamp_cell(*self.view_pos_to_cell(event.pos()))
                self.update_rect_preview(x, y)

            elif rect_active and self.rect_start is not None and event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
                x, y = self.clamp_cell(*self.view_pos_to_cell(event.pos()))
                self.apply_rect_fill(self.rect_start, (x, y))
                self.rect_start = None
                self.clear_rect_preview()

            elif not self.rect_select_mode and event.type() == QtCore.QEvent.MouseMove and self.color != 'alternate' and event.buttons() == QtCore.Qt.LeftButton:
                x, y = self.clamp_cell(*self.view_pos_to_cell(event.pos()))
                val = self.im.getpixel((x,y))

                if self.color == 'occupied':
                    val = 0
                elif self.color == 'unoccupied':
                    val = 255
                elif self.color == 'uncertain':
                    val = 200
                # update model with new value
                self.im.putpixel((x,y), val)

                # redraw cell in new color
                color = self.value2color(val)
                self.color_cell(x, y, color)
        return super(MapEditor, self).eventFilter(source, event)

    def view_pos_to_cell(self, pos):
        scene_pos = self.ui.graphicsView.mapToScene(pos)
        x = math.floor(scene_pos.x() / self.pixels_per_cell)
        y = math.floor(scene_pos.y() / self.pixels_per_cell)
        return x, y

    def clamp_cell(self, x, y):
        x = max(0, min(x, self.map_width_cells - 1))
        y = max(0, min(y, self.map_height_cells - 1))
        return x, y

    def handleRectMode(self, state):
        self.rect_select_mode = (state == QtCore.Qt.Checked)
        self.rect_start = None
        self.clear_rect_preview()

    def update_rect_preview(self, x, y):
        if self.rect_start is None:
            return
        x0, y0 = self.rect_start
        xmin, xmax = min(x0, x), max(x0, x)
        ymin, ymax = min(y0, y), max(y0, y)

        px = xmin * self.pixels_per_cell
        py = ymin * self.pixels_per_cell
        pw = (xmax - xmin + 1) * self.pixels_per_cell
        ph = (ymax - ymin + 1) * self.pixels_per_cell

        if self.rect_preview_item is None:
            pen = QPen(Qt.red)
            pen.setWidth(2)
            self.rect_preview_item = self.scene.addRect(px, py, pw, ph, pen)
        else:
            self.rect_preview_item.setRect(px, py, pw, ph)

    def clear_rect_preview(self):
        if self.rect_preview_item is not None:
            self.scene.removeItem(self.rect_preview_item)
            self.rect_preview_item = None

    def apply_rect_fill(self, start, end):
        if self.color == 'occupied':
            val = 0
        elif self.color == 'unoccupied':
            val = 255
        elif self.color == 'uncertain':
            val = 200
        else:
            return

        x0, y0 = start
        x1, y1 = end
        xmin, xmax = min(x0, x1), max(x0, x1)
        ymin, ymax = min(y0, y1), max(y0, y1)

        for x in range(xmin, xmax + 1):
            for y in range(ymin, ymax + 1):
                self.im.putpixel((x, y), val)
                self.color_cell(x, y, self.value2color(val))


    def paintEvent(self, e):
        self.scrollChanged(0)


    def scrollChanged(self, val):
        
        if self.scene.width() and self.scene.height():
            x = int(self.ui.graphicsView.horizontalScrollBar().value() /  self.scene.width() * self.im.size[0])
            y = int(self.ui.graphicsView.verticalScrollBar().value() /  self.scene.height() * self.im.size[1])
            width = int(self.ui.graphicsView.viewport().size().width() /  self.scene.width() * self.im.size[0])
            height = int(self.ui.graphicsView.viewport().size().height() /  self.scene.height() * self.im.size[1])
            self.drawBox(x, y, width, height)


    def drawBox(self, x=5, y=5, width=50, height=50):

        im = self.im.convert("RGBA")
        data = im.tobytes("raw","RGBA")
        qim = QtGui.QImage(data, im.size[0], im.size[1], QtGui.QImage.Format_ARGB32)
        pix = QtGui.QPixmap.fromImage(qim)

        painter = QtGui.QPainter(pix)
        pen = QPen(Qt.red)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(x, y, width, height)

        painter.end()

        self.ui.label_2.setPixmap(pix)
        self.ui.label_2.show()

    def handleColor(self, index):
        self.color = self.ui.colorBox.currentText()

    def handleZoom(self, index):
        self.zoom = self.ui.zoomBox.currentData()
        self.pixels_per_cell = self.min_multiplier * self.zoom 
        self.draw_map()

    def read(self, fn):
        # Read map file
        try:
            self.im = Image.open(fn)
            self.fn = fn
        except:
            fnpgm = fn + '.pgm'
            try:
                self.im = Image.open(fnpgm)
                self.fn = fnpgm
            except:
                print("ERROR: Cannot open file", fn, "or", fnpgm)
                sys.exit(1)
        # Check if the image format is PGM
        if self.im.format != 'PPM':
            print("ERROR: This is not a PGM formatted file.")
            sys.exit(1)

        # Check if the image mode is L
        if self.im.mode != 'L':
            print("ERROR: This PGM file is not of mode L.")
            sys.exit(1)

        # Set map width and height
        self.map_width_cells = self.im.size[0]
        self.map_height_cells = self.im.size[1]

        # Display file information
        self.ui.filename_lbl.setText(self.fn)
        self.ui.width_lbl.setText(str(self.map_width_cells))
        self.ui.height_lbl.setText(str(self.map_height_cells))
        
        # Read YAML file
        yaml_file = os.path.splitext(fn)[0] + '.yaml'
        try:
            with open(yaml_file, 'r') as stream:
                data = yaml.safe_load(stream)
                self.occupied_thresh = data['occupied_thresh']
                self.free_thresh = data['free_thresh']
                self.resolution = data['resolution']
                self.origin_x = data['origin'][0]
                self.origin_y = data['origin'][1]
        except FileNotFoundError:
            print("ERROR: Corresponding YAML file", yaml_file, "is missing.")
            sys.exit(1)
        except Exception as e:
            print("ERROR: Failed to load YAML file:", e)
            sys.exit(1)

    def mapClick(self, event):
        if self.rect_select_mode:
            return

        # get current model value
        x = math.floor(event.scenePos().x() / self.pixels_per_cell)
        y = math.floor(event.scenePos().y() / self.pixels_per_cell)
        val = self.im.getpixel((x,y))

        if self.color == 'occupied':
            val = 0
        elif self.color == 'unoccupied':
            val = 255
        elif self.color == 'uncertain':
            val = 200
        else:
            # determine next value in sequence white->black->gray
            if val <= (255.0 * (1.0 - self.occupied_thresh)):  # if black, become gray
                val = 200
            elif val <= (255.0 * (1.0 - self.free_thresh)):  # else if gray, become white
                val = 255
            else:  # else its white, become black
                val = 0    

        # update model with new value
        self.im.putpixel((x,y), val)    

        # redraw cell in new color
        color = self.value2color(val)

        self.color_cell(x, y, color)


    def value2color(self, val):
        if val > (255.0 * (1.0 - self.free_thresh)):
            return Qt.white
        elif val > (255.0 * (1.0 - self.occupied_thresh)):
            return Qt.gray
        else:
            return Qt.black

    def color_cell(self, x, y, color):
        pen = QPen(color)
        pen.setWidth(1)
        if self.pixels_per_cell > 10:
            pen = QPen(Qt.lightGray)
        brush = QBrush(color)
        #x = x * self.pixels_per_cell
        #y = y * self.pixels_per_cell
  
        qrect = self.grids[x][y]
        qrect.setBrush(brush)
        qrect.setPen(pen)

        
    def add_cell(self, x, y, color):
        pen = QPen(color)
        pen.setWidth(1)
        if self.pixels_per_cell > 10:
            pen = QPen(Qt.lightGray)
        brush = QBrush(color)
        x = x * self.pixels_per_cell
        y = y * self.pixels_per_cell
        return self.scene.addRect(x, y, self.pixels_per_cell, self.pixels_per_cell, pen, brush)


    def draw_map(self):
        self.rect_start = None
        self.rect_preview_item = None
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.scene.mousePressEvent = self.mapClick
        self.grids = []

        # draw the cells
        self.scene.clear()
        for x in range(0,self.map_width_cells):
            grid_col = []
            for y in range(0, self.map_height_cells):
                val = self.im.getpixel((x,y))
                color = self.value2color(val)
                qrect = self.add_cell(x,y,color)
                grid_col.append(qrect)
            self.grids.append(grid_col)

        # draw the grid lines
        if self.pixels_per_cell > 10:
            pen = QPen(Qt.lightGray)
            pen.setWidth(1)
            pixel_width = self.map_width_cells * self.pixels_per_cell
            pixel_height =self. map_height_cells * self.pixels_per_cell
            for x in range(0, pixel_width, self.pixels_per_cell):
                self.scene.addLine(x, 0, x, pixel_height, pen)
            for y in range(0, pixel_height, self.pixels_per_cell):
                self.scene.addLine(0, y, pixel_width, y, pen)

    def closeEvent(self, event):
        self.close()

    def saveEvent(self, event):
        #self.im.save("map_old.pgm")
        self.im.save(self.fn)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('ERROR:  Must provide map file name - with or without .pgm extension.')
        print()
        print('     $ python MapEditor.py map_file_name')
        print()
    app = QtWidgets.QApplication(sys.argv)
    window = MapEditor(sys.argv[1])
    window.show()
    sys.exit(app.exec_())
