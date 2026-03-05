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
 This script initializes the plugin, making it known to QGIS.
"""

__author__ = 'Daniel Hulshof Saint Martin'
__date__ = '2026-03-05'
__copyright__ = '(C) 2026 by Daniel Hulshof Saint Martin'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load ContourLines class from file contour_lines.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .contour_lines import ContourLinesPlugin
    return ContourLinesPlugin(iface)
