# -*- coding: utf-8 -*-

"""Main module."""

import logging
import time
import queue

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *

from pythonosc import osc_server
from pythonosc.dispatcher import Dispatcher


logger = logging.getLogger(__name__)


def get_vbox_layout():
    vbox = QVBoxLayout()
    vbox.setSpacing(1)
    vbox.setContentsMargins(2, 2, 2, 2)
    return vbox


class ParameterWidget(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent=parent)

        vbox = get_vbox_layout()

        self.dial = QSlider(Qt.Horizontal)
        self.dial.setMinimum(0)
        self.dial.setMaximum(1024)

        sizePolicy = QSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dial.setSizePolicy(sizePolicy)

        vbox.addWidget(self.dial)

        self.value_label = QLabel()
        self.value_label.setAlignment(Qt.AlignCenter)

        vbox.addWidget(self.value_label)

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)

        vbox.addWidget(self.name_label)

        self.setLayout(vbox)

    def setNameLabel(self, label):
        self.name_label.setText(label)

    def setValueLabel(self, label):
        self.value_label.setText(label)

    def setValue(self, value):
        self.dial.setValue(int(value * 1024))

    def paintEvent(self, evt):
        super(ParameterWidget, self).paintEvent(evt)
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        s = self.style()
        s.drawPrimitive(QStyle.PE_Widget, opt, p, self)


class ParametersGrid(QWidget):

    def __init__(self, rows, cols, parent=None):
        QWidget.__init__(self, parent=parent)
        self.parameters = []
        layout = QGridLayout()
        layout.setSpacing(0)

        for row in range(rows):
            for col in range(cols):
                param = ParameterWidget()
                layout.addWidget(param, row, col)
                self.parameters.append(param)

        self.setLayout(layout)


class ControlWidget(QWidget):

    def __init__(self, rows, cols, parent=None):
        QWidget.__init__(self, parent=parent)

        vbox = get_vbox_layout()

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)

        vbox.addWidget(self.name_label)

        self.parameters_grid = ParametersGrid(rows, cols)
        vbox.addWidget(self.parameters_grid)

        self.bypass_button = QPushButton("Bypass")
        self.bypass_button.setCheckable(True)

        vbox.addWidget(self.bypass_button)

        self.learn_button = QPushButton("Learn")
        self.learn_button.setCheckable(True)

        vbox.addWidget(self.learn_button)

        self.setLayout(vbox)

    def setControlName(self, name):
        self.name_label.setText(name)

    def setLearnActive(self, active):
        self.learn_button.setChecked(active)

    def setBypassActive(self, active):
        self.bypass_button.setChecked(active)

    def getParameter(self, num):
        return self.parameters_grid.parameters[num-1]

    def getParameters(self):
        return self.parameters_grid.parameters


class MainWindow(QMainWindow):

    def __init__(self, cfg, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        screen = QApplication.instance().desktop().screenGeometry(1)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.move(screen.left(), screen.top())

        self.cfg_ctl_osc = cfg_ctl_osc = cfg['controller_osc']
        self.cfg_global = cfg_global = cfg['global']

        rows = cfg_global['rows']
        cols = cfg_global['cols']

        self.ctl_widget = ControlWidget(rows, cols)

        for pos, param in enumerate(self.ctl_widget.getParameters()):
            param.setNameLabel('')
            param.setValueLabel('')
            param.setValue(0)

        logger.info('Initializing controller osc server on {}:{}'.format(
            cfg_ctl_osc['remote_ip'], cfg_ctl_osc['remote_port']
        ))
        self.setCentralWidget(self.ctl_widget)

    def on_message(self, addr, args):
        if addr == '/fx/learn':
            self.ctl_widget.setLearnActive(bool(args[0]))
        if addr == '/fx/bypass':
            self.ctl_widget.setBypassActive(bool(args[0]))
        elif addr == '/fx/name':
            self.ctl_widget.setControlName(args[0])
        elif addr.startswith('/fx/param/'):
            fields = addr.split('/')
            target_param = int(fields[-2])
            param_attr = fields[-1]
            try:
                param = self.ctl_widget.getParameter(target_param)
            except IndexError:
                pass
            else:
                if param_attr == 'val':
                    param.setValue(args[0])
                elif param_attr == 'str':
                    param.setValueLabel(args[0])
                elif param_attr == 'name':
                    param.setNameLabel(args[0])
        elif addr == '/toggle_ui':
            if self.isVisible():
                self.hide()
            else:
                self.show()


class MessageServerThread(QThread):

    message_received = Signal(str, object)

    def __init__(self, recv_queue):
        QThread.__init__(self)
        self.recv_queue = recv_queue
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            try:
                msg = self.recv_queue.get(timeout=1)
            except queue.Empty:
                continue
            addr, args = msg
            self.handle(addr, *args)

    def stop(self):
        self.running = False

    def handle(self, addr, *args):
        self.message_received.emit(addr, args)


class OSCServerThread(QThread):

    message_received = Signal(str, object)

    def __init__(self, addr):
        QThread.__init__(self)
        self.dispatcher = Dispatcher()
        self.dispatcher.set_default_handler(self.handle)
        self.server = osc_server.BlockingOSCUDPServer(addr, self.dispatcher)

    def run(self):
        self.server.serve_forever()

    def handle(self, addr, *args):
        self.message_received.emit(addr, args)


def get_app():
    app = QApplication([])
    app.setStyle('fusion')
    app.setWindowIcon(QIcon("Multimedia-volume-control.svg"))
    app.setStyleSheet('''
* {
  font-family: Arial;
  font-size: 11px;
  font-weight: Normal;
}
    ''')

    return app


def get_window(cfg, recv_queue):
    window = MainWindow(cfg)
    message_server_thread = MessageServerThread(recv_queue)
    message_server_thread.message_received.connect(window.on_message)

    frameGm = window.frameGeometry()
    monitor = QDesktopWidget().screenGeometry(0)
    frameGm.moveCenter(monitor.center())
    window.move(frameGm.topLeft())

    message_server_thread.start()
    window.message_server_thread = message_server_thread

    window.show()
    print('*********************window')
    return window
