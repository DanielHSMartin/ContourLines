# -*- coding: utf-8 -*-

"""
/***************************************************************************
 ContourLines
                                 A QGIS plugin
 Generates contour lines from Copernicus GLO-30 worldwide elevation data
                              -------------------
        begin                : 2026-03-05
        copyright            : (C) 2026 by Daniel Hulshof Saint Martin
        email                : daniel.hulshof@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Daniel Hulshof Saint Martin'
__date__ = '2026-03-05'
__copyright__ = '(C) 2026 by Daniel Hulshof Saint Martin'

__revision__ = '$Format:%H$'

import os
import sys

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from qgis.core import QgsApplication
import processing

from .contour_lines_provider import ContourLinesProvider

cmd_folder = os.path.dirname(__file__)

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class ContourLinesPlugin(object):

    def __init__(self, iface):
        self.provider = None
        self.iface = iface

    def initProcessing(self):
        """Init Processing provider for QGIS >= 3.8."""
        self.provider = ContourLinesProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

        icon = os.path.join(os.path.join(cmd_folder, 'logo.png'))
        self.action = QAction(
            QIcon(icon),
            "Contour Lines",
            self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Contour Lines", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
        self.iface.removePluginMenu("&Contour Lines", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        processing.execAlgorithmDialog("Contour Lines:Contour Lines")
