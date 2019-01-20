import logging
import sqlite3
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
if sys.platform == 'win32':
    import numpy.core._dtype_ctypes #don't remove this line, pyinstaller need this
from PySide2 import QtWidgets
from PySide2 import QtCore
from PySide2.QtCore import QPoint
from PySide2.QtCore import QSortFilterProxyModel
from PySide2.QtCore import QItemSelectionModel
from PySide2.QtCore import QRect
from PySide2.QtCore import QSize
from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QIntValidator
from PySide2.QtGui import QStandardItemModel
from PySide2.QtGui import QStandardItem
from PySide2.QtGui import QPixmap
from PySide2.QtGui import QRegion
from PySide2.QtGui import QKeySequence
from PySide2.QtGui import QPainter
from PySide2.QtGui import QPen
from PySide2.QtWidgets import QTableView, QLineEdit
from PySide2.QtWidgets import QToolButton
from PySide2.QtWidgets import QWidget
from PySide2.QtWidgets import QApplication
from PySide2.QtWidgets import QDesktopWidget
from PySide2.QtWidgets import QFileDialog
from PySide2.QtWidgets import QHBoxLayout
from PySide2.QtWidgets import QLabel
from PySide2.QtWidgets import QMessageBox
from PySide2.QtWidgets import QPushButton
from PySide2.QtWidgets import QShortcut
from PySide2.QtWidgets import QVBoxLayout


def order_points(point_list):
    point_list = sorted(point_list, key=lambda x: x[0])
    a1 = sorted([*point_list[:2]], key=lambda x: x[1])
    a2 = sorted([*point_list[2:]], key=lambda x: x[1])
    return np.array([a1[0], a2[0], a2[1], a1[1]], np.int)

class DBLabelText:
    def __init__(self, lable_data_path):
        self.conn = sqlite3.connect(lable_data_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute(r'''
        CREATE TABLE IF NOT EXISTS label_text (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            img_name TEXT NOT NULL, --图片文件名
            x1 INTEGER NOT NULL, --左上角x坐标
            y1 INTEGER NOT NULL, --左上角y坐标
            x2 INTEGER NOT NULL, --右上角x坐标
            y2 INTEGER NOT NULL, --右上角y坐标
            x3 INTEGER NOT NULL, --右下角x坐标
            y3 INTEGER NOT NULL, --右下角y坐标
            x4 INTEGER NOT NULL, --左下角x坐标
            y4 INTEGER NOT NULL, --左下角y坐标
            img_text TEXT NOT NULL, -- 文本内容
            tsp INTEGER NOT NULL --最后一次修改的时间戳
        );
    ''')

        self.cursor.execute(f'''
        CREATE INDEX IF NOT EXISTS `idx_label_text_img_name` ON `label_text` (`img_name` ASC);
        ''')

    def get_all_text(self, img_name):
        result_list = self.cursor.execute(r'''
        SELECT id,x1,y1,x2,y2,x3,y3,x4,y4,img_text
        FROM label_text
        WHERE img_name = ?
        ORDER BY id
        ''', (img_name,)).fetchall()
        result = []
        if result_list:
            for id,x1,y1,x2,y2,x3,y3,x4,y4,img_text in result_list:
                result.append([id, np.array([(x1,y1), (x2,y2), (x3,y3), (x4,y4)], dtype=np.int).reshape((4,2)), img_text])
        return result

    def add_text(self, img_name, point_list, img_text):
        self.cursor.execute(r'''
        INSERT INTO label_text (img_name,x1,y1,x2,y2,x3,y3,x4,y4,img_text,tsp) 
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (img_name, *point_list.flatten().tolist(), img_text, int(time.time())))
        self.conn.commit()
        return self.cursor.lastrowid

    def del_text(self, img_name, id):
        self.cursor.execute(r'''
        DELETE FROM label_text WHERE img_name=? AND id=?;
        ''', (img_name, id))
        self.conn.commit()

    def update_text(self, img_name, id, img_text):
        self.cursor.execute(r'''
        UPDATE label_text SET img_text=? WHERE img_name=? AND id=?
        ''', (img_text, img_name, id))
        self.conn.commit()

    def update_points(self, img_name, id, point_list):
        self.cursor.execute(r'''
        UPDATE label_text SET x1=?, y1=?, x2=?, y2=?, x3=?, y3=?, x4=?, y4=?
        WHERE img_name=? AND id=?
        ''', (*point_list.flatten().tolist(), img_name, id))
        self.conn.commit()

    def __del__(self):
        self.conn.close()

class DragButton(QToolButton):
    def __init__(self, parent=None):
        super(DragButton, self).__init__(parent)
        self.setStyleSheet('''
            background-color: red;
        ''')

        self.setFixedSize(10, 10)
        self.border_size = self.parent().size()

    def mousePressEvent(self, event):
        self.setStyleSheet('''
            background-color: yellow;
        ''')
        self.__mousePressPos = None
        self.__mouseMovePos = None
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
            self.__mouseMovePos = event.globalPos()
        super(DragButton, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            currPos = self.mapToGlobal(self.pos())
            globalPos = event.globalPos()
            diff = globalPos - self.__mouseMovePos
            newPos = self.mapFromGlobal(currPos + diff)

            center_point = [newPos.x() + self.width() / 2,
                            newPos.y() + self.height() / 2]
            if center_point[0] > self.border_size.width()-10:
                center_point[0] = self.border_size.width()-10
            if center_point[0] < 10:
                center_point[0] = 10

            if center_point[1] > self.border_size.height()-10:
                center_point[1] = self.border_size.height()-10
            if center_point[1] < 10:
                center_point[1] = 10

            self.move(QPoint(
                center_point[0] - self.width() / 2,
                center_point[1] - self.height() / 2
            ))
            self.__mouseMovePos = globalPos
            self.parent().update_points()

        super(DragButton, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setStyleSheet('''
            background-color: red;
        ''')
        if self.__mousePressPos is not None:
            moved = event.globalPos() - self.__mousePressPos
            if moved.manhattanLength() > 3:
                event.ignore()
                return
        super(DragButton, self).mouseReleaseEvent(event)

    def resizeEvent(self, event):
        self.setMask(QRegion(self.rect(), QRegion.Ellipse))
        QtWidgets.QToolButton.resizeEvent(self, event)

class ImageLabel(QLabel):
    def __init__(self, parent):
        super(ImageLabel, self).__init__(parent)

        self.img_extra_border_size = (50, 50)
        self.scaled_img = None
        self.scaled_ratio = None
        self.scaled_img_rect = None
        self.img_all_text = None
        self.img_activate_idx = None

        self.btn_point1 = DragButton(self)
        self.btn_point2 = DragButton(self)
        self.btn_point3 = DragButton(self)
        self.btn_point4 = DragButton(self)

        self.btn_point1.setVisible(False)
        self.btn_point2.setVisible(False)
        self.btn_point3.setVisible(False)
        self.btn_point4.setVisible(False)

    def show_activate_img(self, img, all_text, activate_idx):
        self.scaled_img = None
        self.scaled_ratio = None
        self.scaled_img_rect = None
        self.img_all_text = []
        self.img_activate_idx = None

        self.btn_point1.setVisible(False)
        self.btn_point2.setVisible(False)
        self.btn_point3.setVisible(False)
        self.btn_point4.setVisible(False)

        if img:
            scaled_size = QSize(
                self.size().width()-self.img_extra_border_size[1]*2,
                self.size().height()-self.img_extra_border_size[0]*2
            )
            self.scaled_img = img.scaled(scaled_size, Qt.KeepAspectRatio)

            self.scaled_ratio = self.scaled_img.width() / img.width()

            self.scaled_img_rect = QRect(
                self.img_extra_border_size[0],
                self.img_extra_border_size[1],
                self.scaled_img.width(),
                self.scaled_img.height()
            )

            self.img_activate_idx = activate_idx
            for idx, point_list, img_text in all_text:
                point_list = point_list.astype(np.float)
                point_list *= self.scaled_ratio
                point_list = point_list.astype(np.int)

                point_list -= self.btn_point1.width() // 2
                point_list[:, 0] += self.img_extra_border_size[1]
                point_list[:, 1] += self.img_extra_border_size[0]
                for p in point_list:
                    if p[0] < 10:
                        p[0] = 10
                    elif p[0] > self.size().width()-10:
                        p[0] = self.size().width()-10

                    if p[1] < 10:
                        p[1] = 10
                    elif p[1] > self.size().height()-10:
                        p[1] = self.size().height()-10

                self.img_all_text.append([idx, point_list, img_text])

                if activate_idx == idx:
                    self.btn_point1.move(QPoint(point_list[0, 0], point_list[0, 1]))
                    self.btn_point2.move(QPoint(point_list[1, 0], point_list[1, 1]))
                    self.btn_point3.move(QPoint(point_list[2, 0], point_list[2, 1]))
                    self.btn_point4.move(QPoint(point_list[3, 0], point_list[3, 1]))

                    self.btn_point1.setVisible(True)
                    self.btn_point2.setVisible(True)
                    self.btn_point3.setVisible(True)
                    self.btn_point4.setVisible(True)

                    self.btn_point1.border_size = self.size()
                    self.btn_point2.border_size = self.size()
                    self.btn_point3.border_size = self.size()
                    self.btn_point4.border_size = self.size()

        self.repaint()

    def update_points(self):
        if self.img_activate_idx is None or self.scaled_img is None:
            return

        pos1 = self.btn_point1.pos()
        pos2 = self.btn_point2.pos()
        pos3 = self.btn_point3.pos()
        pos4 = self.btn_point4.pos()
        point_list = np.array([(pos1.x(), pos1.y()),
                               (pos2.x(), pos2.y()),
                               (pos3.x(), pos3.y()),
                               (pos4.x(), pos4.y())])
        point_list = order_points(point_list)

        for idx, (id, _, _) in enumerate(self.img_all_text):
            if id != self.img_activate_idx:
                continue
            self.img_all_text[idx][1] = point_list
            break

        point_list = deepcopy(point_list)
        point_list[:, 0] -= self.img_extra_border_size[1]
        point_list[:, 1] -= self.img_extra_border_size[0]
        point_list += self.btn_point1.width() // 2
        point_list = point_list.astype(np.float)
        point_list /= self.scaled_ratio
        point_list = point_list.astype(np.int)
        point_list += 1

        self.parent().update_points(self.img_activate_idx, point_list)
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        painter.setPen(Qt.NoPen)
        painter.fillRect(self.rect(), QColor(190, 190, 190, 255))

        if self.scaled_img:
            painter.drawPixmap(self.scaled_img_rect, self.scaled_img)

            for idx, point_list, img_text in self.img_all_text:
                point_list = point_list + self.btn_point1.width() // 2
                if idx == self.img_activate_idx:
                    painter.setPen(QPen(Qt.red, 1))
                else:
                    painter.setPen(QPen(Qt.green, 1))
                painter.drawLine(
                    point_list[0, 0],
                    point_list[0, 1],
                    point_list[1, 0],
                    point_list[1, 1]
                )
                painter.drawLine(
                    point_list[1, 0],
                    point_list[1, 1],
                    point_list[2, 0],
                    point_list[2, 1]
                )
                painter.drawLine(
                    point_list[2, 0],
                    point_list[2, 1],
                    point_list[3, 0],
                    point_list[3, 1]
                )
                painter.drawLine(
                    point_list[3, 0],
                    point_list[3, 1],
                    point_list[0, 0],
                    point_list[0, 1]
                )

        painter.end()


class TextTableView(QTableView):
    def __init__(self, parent):
        super(TextTableView, self).__init__(parent)

        self.model = QStandardItemModel(self)
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.setModel(self.proxy)

        self.selectionModel().selectionChanged.connect(self.on_select_change)
        self.model.dataChanged.connect(self.on_text_change)

        self.all_text_dict = {}

    def show_activate_img(self, all_text, activate_idx):
        self.all_text_dict = {}
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['文本', '编号'])

        self.setAutoScroll(True)
        self.setColumnWidth(0, 300)
        self.setColumnWidth(1, 0)
        self.setSelectionMode(QTableView.SingleSelection)
        for col_id, (idx, point_list, img_text) in enumerate(all_text):
            self.all_text_dict[idx] = img_text

            it1 = QStandardItem(img_text)
            it1.setEditable(True)
            self.model.setItem(col_id, 0, it1)

            it2 = QStandardItem(str(idx))
            it2.setEditable(False)
            self.model.setItem(col_id, 1, it2)

            if activate_idx == idx:
                self.selectionModel().select(self.model.index(col_id, 0), QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)

    def on_select_change(self):
        select_row_indexs = self.selectionModel().selectedIndexes()
        if not select_row_indexs:
            return

        row_index = select_row_indexs[0]
        row = row_index.row()
        activate_idx = row_index.sibling(row, 1).data()
        self.parent().on_activate_idx_change(int(activate_idx))

    def remove_selected_row(self):
        select_row_indexs = self.selectionModel().selectedIndexes()
        if not select_row_indexs:
            return None

        row_index = select_row_indexs[0]
        row = row_index.row()
        img_idx = row_index.sibling(row, 1).data()
        self.model.removeRow(row)
        return int(img_idx)

    def on_text_change(self, idx1, idx2):
        row = idx1.row()
        new_text = idx1.sibling(row, 0).data()
        activate_idx = idx1.sibling(row, 1).data()
        if activate_idx is not None:
            activate_idx = int(activate_idx)
            if self.all_text_dict[activate_idx] != new_text:
                self.parent().on_text_change(activate_idx, new_text)

class MainWindow(QWidget):
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        # 界面配置
        self.setWindowTitle('文字识别标注工具')
        self.setFixedSize(1200, 800)
        self.move_to_center()

        #
        self.label_img = ImageLabel(self)
        self.label_img.setAlignment(Qt.AlignCenter)
        self.label_img.setText('没有选择任何图片')
        self.label_img.setFixedWidth(900)
        self.label_img.setFixedHeight(750)

        #
        self.label_status_running1 = QLabel(self)
        self.label_status_running1.setAlignment(Qt.AlignLeft)
        self.label_status_running1.setText('请选择需要标注的目录')

        self.label_status_page_number_validator = QIntValidator()
        self.label_status_page_number = QLineEdit(self)
        self.label_status_page_number.setMaximumWidth(50)
        self.label_status_page_number.setValidator(
            self.label_status_page_number_validator)
        self.label_status_page_number.hide()
        self.label_status_page_number.returnPressed.connect(self.on_page_jump)

        self.label_status_running2 = QLabel(self)
        self.label_status_running2.setAlignment(Qt.AlignLeft)
        self.label_status_running2.setText('张')
        self.label_status_running2.hide()


        self.btn_select_dir = QPushButton(self)
        self.btn_select_dir.setText('选择目录...')
        self.btn_select_dir.clicked.connect(self.on_select_diectory)

        self.btn_prev_img = QPushButton(self)
        self.btn_prev_img.setText('上一张')
        self.btn_prev_img.clicked.connect(self.on_prev_img)
        self.connect(
            QShortcut(QKeySequence(QtCore.Qt.Key_Left), self),
            QtCore.SIGNAL('activated()'),
            self.btn_prev_img.click
        )

        self.btn_next_img = QPushButton(self)
        self.btn_next_img.setText('下一张')
        self.btn_next_img.clicked.connect(self.on_next_img)
        self.connect(
            QShortcut(QKeySequence(Qt.Key_Right), self),
            QtCore.SIGNAL('activated()'),
            self.btn_next_img.click
        )

        self.btn_new_text = QPushButton(self)
        self.btn_new_text.setText('新增')
        self.btn_new_text.clicked.connect(self.on_add_text)

        self.btn_del_text = QPushButton(self)
        self.btn_del_text.setText('删除')
        self.btn_del_text.clicked.connect(self.on_del_text)

        self.tableview_text = TextTableView(self)

        # 布局
        layout_root = QHBoxLayout()
        layout_col1 = QVBoxLayout()
        layout_col2 = QVBoxLayout()
        layout_root.addLayout(layout_col1)
        layout_root.addLayout(layout_col2)

        layout_col1.addWidget(self.label_img)
        layout_col1_row2 = QHBoxLayout()
        layout_col1_row2.setSpacing(1)
        layout_col1_row2.setAlignment(Qt.AlignLeft)
        layout_col1_row2.addWidget(self.label_status_running1, 0, Qt.AlignRight)
        layout_col1_row2.addWidget(self.label_status_page_number, 0, Qt.AlignRight)
        layout_col1_row2.addWidget(self.label_status_running2, 0, Qt.AlignRight)

        layout_col1.addLayout(layout_col1_row2)

        layout_col2_row1 = QHBoxLayout()
        layout_col2_row1.addWidget(self.btn_select_dir)

        layout_col2_row2 = QHBoxLayout()
        layout_col2_row2.addWidget(self.btn_prev_img)
        layout_col2_row2.addWidget(self.btn_next_img)

        layout_col2_row3 = QHBoxLayout()
        layout_col2_row3.addWidget(self.btn_new_text)
        layout_col2_row3.addWidget(self.btn_del_text)

        layout_col2.addLayout(layout_col2_row1)
        layout_col2.addLayout(layout_col2_row2)
        layout_col2.addLayout(layout_col2_row3)
        layout_col2.addWidget(self.tableview_text)

        self.setLayout(layout_root)

        self.directory = None
        self.all_img_file = []
        self.all_img_file_index = 0
        self.db_label = None

        self.update_btn_status()

    def move_to_center(self):
        screen = QDesktopWidget().screenGeometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) / 2,(screen.height() - size.height()) / 2)

    def update_btn_status(self):
        try:
            self.label_status_page_number.setEnabled(False)
            self.btn_prev_img.setEnabled(False)
            self.btn_next_img.setEnabled(False)
            self.btn_new_text.setEnabled(False)
            self.btn_del_text.setEnabled(False)

            if not self.all_img_file:
                self.label_status_running1.setText('请选择需要标注的目录')
                self.label_status_page_number.hide()
                self.label_status_running2.hide()
            else:
                img_name = self.all_img_file[self.all_img_file_index]

                self.label_status_page_number.show()
                self.label_status_running2.show()
                self.label_status_page_number_validator.setRange(1, len(self.all_img_file))
                self.label_status_page_number.setText(f'{self.all_img_file_index+1}')
                self.label_status_running1.setText( f'当前图片: {img_name} ({self.all_img_file_index + 1}/{len(self.all_img_file)}) 跳转到')
                self.label_status_running2.setText(f'张')
                self.label_status_page_number.setEnabled(True)

                if self.all_img_file_index == 0:
                    self.btn_prev_img.setEnabled(False)
                else:
                    self.btn_prev_img.setEnabled(True)

                if self.all_img_file_index == len(self.all_img_file) - 1:
                    self.btn_next_img.setEnabled(False)
                else:
                    self.btn_next_img.setEnabled(True)

                self.btn_new_text.setEnabled(True)
                self.btn_del_text.setEnabled(True)
        except:
            logging.exception('update_btn_status exception')

    def on_select_diectory(self):
        try:
            self.all_img_file = []
            self.all_img_file_index = 0
            self.db_label = None
            self.label_img.show_activate_img(None, [], None)

            self.directory = QFileDialog.getExistingDirectory(self, '选择目录')
            self.setWindowTitle(f'文字识别标注工具: {self.directory}')

            self.get_all_img_file()
            if len(self.all_img_file) <= 0:
                QMessageBox.information(
                    self,
                    '<提示>',
                    f'{self.directory}\n目录下没有找到图片文件',
                    QMessageBox.Ok
                )
                return

            self.read_label_file()
            self.show_img()
        finally:
            self.update_btn_status()

    def get_all_img_file(self):
        self.all_img_file_index = 0
        self.all_img_file = sorted([str(x.name) for x in Path(self.directory).iterdir(
        ) if x.is_file() and x.suffix.upper() in ['.JPG', '.JPEG', '.BMP', '.PNG']])

    def read_label_file(self):
        label_file = Path(self.directory).joinpath('label.sqllite3')
        self.db_label = DBLabelText(str(label_file))

    def on_next_img(self):
        try:
            self.all_img_file_index += 1
            self.show_img()
        finally:
            self.update_btn_status()

    def on_prev_img(self):
        try:
            self.all_img_file_index -= 1
            self.show_img()
        finally:
            self.update_btn_status()

    def on_page_jump(self):
        try:
            page_num = int(self.label_status_page_number.text())
            if page_num >= 1 and page_num <= len(self.all_img_file):
                self.all_img_file_index = page_num - 1
            self.show_img()
            self.setFocus()
        finally:
            self.update_btn_status()

    def on_add_text(self):
        try:
            if not self.all_img_file:
                return

            img_name = self.all_img_file[self.all_img_file_index]
            point_list = np.array([(50, 50),
                                   (self.label_img.width() - 50, 50),
                                   (self.label_img.width() - 50, self.label_img.height() - 50),
                                   (50, self.label_img.height() - 50)
                                   ])
            img_text = ''
            activate_idx = self.db_label.add_text(img_name, point_list, img_text)
            self.show_img(activate_idx)
        finally:
            self.update_btn_status()

    def on_del_text(self):
        try:
            img_idx = self.tableview_text.remove_selected_row()
            if img_idx is not None:
                img_name = self.all_img_file[self.all_img_file_index]
                activate_idx = self.db_label.del_text(img_name, img_idx)
                self.show_img(activate_idx)
        finally:
            self.update_btn_status()

    def show_img(self, activate_idx=None, img_update=True, table_update=True):
        img_name = self.all_img_file[self.all_img_file_index]

        all_text = self.db_label.get_all_text(img_name)

        if img_update:
            img_path = Path(self.directory).joinpath(img_name)
            img = QPixmap(str(img_path))

            self.label_img.show_activate_img(img, all_text, activate_idx)

        if table_update:
            self.tableview_text.show_activate_img(all_text, activate_idx)

    def update_points(self, activate_idx, point_list):
        if self.all_img_file:
            img_name = self.all_img_file[self.all_img_file_index]
            self.db_label.update_points(img_name, activate_idx, point_list)

    def on_activate_idx_change(self, activate_idx):
        self.show_img(activate_idx, table_update=False)

    def on_text_change(self, activate_idx, new_text):
        img_name = self.all_img_file[self.all_img_file_index]
        self.db_label.update_text(img_name, activate_idx, new_text)
        self.show_img(activate_idx, table_update=False)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    widget = MainWindow()
    widget.show()
    sys.exit(app.exec_())
