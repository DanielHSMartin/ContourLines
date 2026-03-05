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
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider
from .contour_lines_algorithm import ContourLinesAlgorithm


class ContourLinesProvider(QgsProcessingProvider):

    def __init__(self):
        QgsProcessingProvider.__init__(self)

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(ContourLinesAlgorithm())

    def id(self):
        return 'Contour Lines'

    def name(self):
        return self.tr('Contour Lines')

    def icon(self):
        cmd_folder = os.path.dirname(__file__)
        icon = QIcon(os.path.join(cmd_folder, 'logo.png'))
        return icon

    def longName(self):
        return self.name()
