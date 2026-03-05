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

import math
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse
import tempfile
from osgeo import gdal, ogr, osr
from .gdal_calc import Calc
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsAuthMethodConfig,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProcessingAlgorithm,
    QgsProcessingParameterAuthConfig,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingParameterColor,
    QgsProcessingParameterEnum,
    QgsProject,
    QgsRuleBasedRenderer,
    QgsSymbol,
    QgsSymbolLayerReference,
    QgsSymbolLayerId,
    QgsTextMaskSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling
)

# Copernicus GLO-30 DEM base URL (AWS Open Data, no authentication required)
# https://registry.opendata.aws/copernicus-dem/
COPERNICUS_BASE_URL = 'https://copernicus-dem-30m.s3.amazonaws.com/'


class ContourLinesAlgorithm(QgsProcessingAlgorithm):

    # Parameter constants
    AREA_OF_INTEREST = 'AREA_OF_INTEREST'
    INTERVAL = 'INTERVAL'
    SMOOTHING = 'SMOOTHING'
    COLOR = 'COLOR'
    PROXY_AUTH = 'PROXY_AUTH'

    def __init__(self):
        super().__init__()
        # Temporary storage folder for downloaded and intermediate raster files
        self.temp_dir = os.path.join(tempfile.gettempdir(), 'ContourLines')
        self.status_total = 0.0
        self.progress = 0.0

    def flags(self):
        if Qgis.QGIS_VERSION_INT >= 40000:
            return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading
        else:
            return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def initAlgorithm(self, config):

        # Area of interest extent
        self.addParameter(
            QgsProcessingParameterExtent(
                self.AREA_OF_INTEREST,
                'Area of Interest',
                optional=False))

        # Contour interval in metres
        self.addParameter(
            QgsProcessingParameterNumber(
                name=self.INTERVAL,
                description=self.tr('Contour interval (metres)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=10,
                minValue=1,
                maxValue=1000,
                optional=False
            )
        )

        # Terrain smoothing level
        self.addParameter(
            QgsProcessingParameterEnum(
                name=self.SMOOTHING,
                description=self.tr('Terrain smoothing level'),
                options=['None', 'Low', 'Medium', 'High'],
                defaultValue='Medium',
                usesStaticStrings=True,
                optional=False
            )
        )

        # Contour line colour
        self.addParameter(
            QgsProcessingParameterColor(
                name=self.COLOR,
                description=self.tr('Contour line colour'),
                defaultValue='#cc7700cc',
                opacityEnabled=True,
                optional=False
            )
        )

        # Optional proxy authentication
        self.addParameter(
            QgsProcessingParameterAuthConfig(
                name=self.PROXY_AUTH,
                description=self.tr('Proxy authentication (optional)'),
                optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        # Initialise progress tracking
        self.status_total = 0.0
        self.progress = 0.0
        os.makedirs(self.temp_dir, exist_ok=True)
        feedback.pushInfo('\nTemporary folder: ' + self.temp_dir)

        # Load area of interest in EPSG:4326
        area_of_interest = self.parameterAsExtent(
            parameters,
            self.AREA_OF_INTEREST,
            context,
            crs=QgsCoordinateReferenceSystem('EPSG:4326'))

        # Validate extent
        if area_of_interest.isNull() or not area_of_interest.isFinite():
            raise ValueError(
                self.tr(
                    'Invalid area of interest (NaN values detected).\n\n'
                    'This can happen when:\n'
                    '- A polygon layer is selected but has not been saved\n'
                    '- The layer is empty or has no valid geometries\n\n'
                    'Please:\n'
                    '1. Draw a rectangle directly using the extent tool, OR\n'
                    '2. If using a polygon layer, make sure it is saved first'))

        aoi_geometry = QgsGeometry.fromRect(area_of_interest)

        if aoi_geometry.isNull() or aoi_geometry.isEmpty():
            raise ValueError(
                self.tr('Could not create the area of interest geometry.'))

        # Write area of interest to a temporary shapefile for gdal.Warp clipping
        aoi_shp_path = os.path.join(self.temp_dir, 'area_of_interest.shp')
        shp_driver = ogr.GetDriverByName('ESRI Shapefile')
        if os.path.exists(aoi_shp_path):
            shp_driver.DeleteDataSource(aoi_shp_path)
        aoi_datasource = shp_driver.CreateDataSource(aoi_shp_path)
        aoi_layer = aoi_datasource.CreateLayer('layer', geom_type=ogr.wkbPolygon)
        feat_defn = aoi_layer.GetLayerDefn()
        feature = ogr.Feature(feat_defn)

        wkt = aoi_geometry.asWkt()
        ogr_geom = ogr.CreateGeometryFromWkt(wkt)
        if ogr_geom is None:
            raise ValueError(
                self.tr('Failed to convert geometry to OGR format. WKT: {}').format(wkt))

        feature.SetGeometry(ogr_geom)
        aoi_layer.CreateFeature(feature)
        aoi_datasource = None

        # Load processing parameters
        interval = self.parameterAsInt(parameters, self.INTERVAL, context)
        smoothing = self.parameterAsString(parameters, self.SMOOTHING, context)
        color = self.parameterAsColor(parameters, self.COLOR, context)

        # Set up proxy opener if authentication config is provided
        proxy_opener = None
        auth_id = self.parameterAsString(parameters, self.PROXY_AUTH, context)
        if auth_id == '':
            feedback.pushInfo('\nNo proxy authentication configured')
        else:
            auth_mgr = QgsApplication.authManager()
            auth_cfg = QgsAuthMethodConfig()
            auth_mgr.loadAuthenticationConfig(auth_id, auth_cfg, True)
            auth_info = auth_cfg.configMap()
            try:
                proxy_host = urlparse(auth_info['realm']).hostname
                proxy_port = urlparse(auth_info['realm']).port
                proxy_user = auth_info['username']
                proxy_pass = auth_info['password']
                proxy_base_url = 'http://{}:{}'.format(proxy_host, proxy_port)
                proxy_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                proxy_mgr.add_password(
                    None, proxy_base_url, proxy_user, proxy_pass)
                proxy_auth_handler = urllib.request.ProxyBasicAuthHandler(proxy_mgr)
                proxy_handler = urllib.request.ProxyHandler(
                    {'http': proxy_base_url, 'https': proxy_base_url})
                proxy_opener = urllib.request.build_opener(
                    proxy_handler, proxy_auth_handler)
                feedback.pushInfo(
                    '\nUsing proxy authentication for user: ' + proxy_user)
            except Exception as e:
                feedback.pushInfo(
                    '\nFailed to load proxy authentication: ' + str(e))

        # ------------------------------------------------------------------ #
        # Determine which Copernicus GLO-30 tiles cover the area of interest. #
        # Tiles are 1° x 1° in EPSG:4326.                                     #
        # Tile name format:                                                    #
        #   Copernicus_DSM_COG_10_{N|S}{lat:02d}_00_{E|W}{lon:03d}_00_DEM    #
        # where lat/lon is the SW corner of the tile.                          #
        # ------------------------------------------------------------------ #
        feedback.pushInfo('\nCalculating required Copernicus GLO-30 tiles')

        south = area_of_interest.yMinimum()
        north = area_of_interest.yMaximum()
        west = area_of_interest.xMinimum()
        east = area_of_interest.xMaximum()

        tile_list = []

        for lat in range(math.floor(south), math.ceil(north)):
            for lon in range(math.floor(west), math.ceil(east)):

                # Tile footprint polygon
                tile_points = [
                    QgsPointXY(lon,     lat),
                    QgsPointXY(lon + 1, lat),
                    QgsPointXY(lon + 1, lat + 1),
                    QgsPointXY(lon,     lat + 1)]
                tile_poly = QgsGeometry.fromPolygonXY([tile_points])

                # Only include tiles that actually intersect the AOI
                if tile_poly.intersection(aoi_geometry).isEmpty():
                    continue

                ns = 'N' if lat >= 0 else 'S'
                ew = 'E' if lon >= 0 else 'W'
                tile_name = 'Copernicus_DSM_COG_10_{}{:02d}_00_{}{:03d}_00_DEM'.format(
                    ns, abs(lat), ew, abs(lon))

                if tile_name not in tile_list:
                    tile_list.append(tile_name)
                    feedback.pushInfo('Required tile: ' + tile_name)

        if not tile_list:
            feedback.pushInfo('\nNo tiles found for the given area of interest.')
            return {}

        # Initialise progress bar
        # Steps: 1 (setup) + 1 per download + 1 per clip + merge + smooth + contour + finish
        steps = 5 + 2 * len(tile_list)
        self.status_total = 100.0 / steps
        self.progress = 0.0

        self.progress += 1
        feedback.setProgress(int(self.progress * self.status_total))

        # ------------------------------------------------------------------ #
        # Download tiles from Copernicus GLO-30 on AWS (no authentication).  #
        # Tiles are served as plain Cloud-Optimized GeoTIFFs — no unzipping. #
        # ------------------------------------------------------------------ #
        for tile_name in tile_list[:]:
            if feedback.isCanceled():
                feedback.pushInfo('\nCancelled by user')
                return {}

            local_tif = os.path.join(self.temp_dir, tile_name + '.tif')
            feedback.pushInfo('\nLooking for tile: ' + tile_name + '.tif')

            if os.path.exists(local_tif):
                feedback.pushInfo('Tile found in cache')
            else:
                tile_url = '{}{}/{}.tif'.format(
                    COPERNICUS_BASE_URL, tile_name, tile_name)
                feedback.pushInfo('Downloading: ' + tile_url)
                try:
                    opener = proxy_opener if proxy_opener else urllib.request.build_opener()
                    with opener.open(tile_url, timeout=60) as response:
                        total_size = int(response.headers.get('Content-Length', 0))
                        chunks = []
                        bytes_received = 0
                        chunk_size = 65536
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            chunks.append(chunk)
                            bytes_received += len(chunk)
                            if total_size > 0:
                                dl_progress = self.progress + bytes_received / total_size
                                feedback.setProgress(
                                    int(dl_progress * self.status_total))
                        content = b''.join(chunks)
                    if content:
                        with open(local_tif, 'wb') as f:
                            f.write(content)
                    else:
                        raise ValueError('Empty response from server')
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        # Tile does not exist (ocean area or withheld tile)
                        feedback.pushInfo(
                            'WARNING: Tile not available (HTTP 404) — '
                            'this may be an ocean area or a restricted tile: '
                            + tile_name)
                    else:
                        feedback.pushInfo(
                            '\nHTTP error downloading tile: ' + str(e))
                        feedback.pushInfo(
                            'URL: ' + tile_url)
                    tile_list.remove(tile_name)
                except Exception as e:
                    feedback.pushInfo('\nError downloading tile: ' + tile_url)
                    feedback.pushInfo('Check proxy settings or internet connection')
                    feedback.pushInfo('You can test the URL manually in a browser')
                    feedback.pushInfo('Error detail: ' + str(e))
                    tile_list.remove(tile_name)

            self.progress += 1
            feedback.setProgress(int(self.progress * self.status_total))

        # ------------------------------------------------------------------ #
        # Clip, merge, smooth and generate contours                           #
        # ------------------------------------------------------------------ #
        if not tile_list:
            feedback.pushInfo('\nNo tiles were downloaded successfully.')
            return {}

        feedback.pushInfo('\nClipping tiles to area of interest')
        clipped_rasters = []

        def gdal_callback(info, *args):
            p = self.progress + info
            feedback.setProgress(int(p * self.status_total))

        for tile_name in tile_list:
            fn_in = os.path.join(self.temp_dir, tile_name + '.tif')
            fn_clip = os.path.join(self.temp_dir, tile_name + '_clip.tif')
            clipped_rasters.append(fn_clip)

            feedback.pushInfo('Clipping: ' + tile_name + '.tif')
            gdal.Warp(
                fn_clip,
                fn_in,
                cutlineDSName=aoi_shp_path,
                cropToCutline=True,
                dstNodata=0,
                srcSRS='EPSG:4326',
                dstSRS='EPSG:4326',
                format='GTiff',
                callback=gdal_callback)

            if feedback.isCanceled():
                feedback.pushInfo('\nCancelled by user')
                return {}

            self.progress += 1
            feedback.setProgress(int(self.progress * self.status_total))

        feedback.pushInfo('\nMerging clipped tiles')
        merged_path = os.path.join(self.temp_dir, 'merged.tif')
        gdal.Warp(
            merged_path,
            clipped_rasters,
            format='GTiff',
            callback=gdal_callback)

        if feedback.isCanceled():
            feedback.pushInfo('\nCancelled by user')
            return {}

        self.progress += 1
        feedback.setProgress(int(self.progress * self.status_total))

        # Apply terrain smoothing
        self._smooth_terrain(smoothing, feedback)

        if feedback.isCanceled():
            feedback.pushInfo('\nCancelled by user')
            return {}

        self.progress += 1
        feedback.setProgress(int(self.progress * self.status_total))

        # Generate contour lines
        feedback.pushInfo('\nGenerating contour lines')
        tmp_shp_dir = tempfile.mkdtemp(dir=self.temp_dir, prefix='contourlines_')
        contour_shp_path = os.path.join(tmp_shp_dir, 'contourlines.shp')

        shp_ds = shp_driver.CreateDataSource(contour_shp_path)
        srs_4326 = osr.SpatialReference()
        srs_4326.ImportFromEPSG(4326)
        srs_4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        contour_layer = shp_ds.CreateLayer('Contour Lines', srs=srs_4326)
        contour_layer.CreateField(ogr.FieldDefn('ID', ogr.OFTInteger))
        contour_layer.CreateField(ogr.FieldDefn('ELEV', ogr.OFTReal))
        type_field = ogr.FieldDefn('TYPE', ogr.OFTString)
        type_field.SetWidth(50)
        contour_layer.CreateField(type_field)

        merged_ds = gdal.Open(merged_path)
        gdal.ContourGenerate(
            merged_ds.GetRasterBand(1),
            interval,
            0,
            [],
            0,
            0,
            contour_layer,
            0,
            1,
            callback=gdal_callback)
        shp_ds = None
        merged_ds = None

        if feedback.isCanceled():
            feedback.pushInfo('\nCancelled by user')
            return {}

        self.progress += 1
        feedback.setProgress(int(self.progress * self.status_total))

        # Reproject to project CRS if needed
        project_crs = context.project().crs()
        if project_crs.isValid() and project_crs.authid().upper() != 'EPSG:4326':
            feedback.pushInfo('\nReprojecting contours to ' + project_crs.authid())
            reproj_dir = tempfile.mkdtemp(dir=self.temp_dir, prefix='contourlines_reproj_')
            reproj_shp_path = os.path.join(reproj_dir, 'contourlines_reproj.shp')
            gdal.VectorTranslate(
                reproj_shp_path,
                contour_shp_path,
                options=gdal.VectorTranslateOptions(
                    dstSRS=project_crs.authid(),
                    reproject=True))
            final_shp_path = reproj_shp_path
        else:
            final_shp_path = contour_shp_path

        # Load the vector layer
        layer = QgsVectorLayer(final_shp_path, 'Contour Lines')
        feedback.pushInfo('Contour lines generated: '
                          + str(len(list(layer.getFeatures()))))

        # ------------------------------------------------------------------ #
        # Apply symbology: rule-based renderer with index and normal contours #
        # ------------------------------------------------------------------ #
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        renderer = QgsRuleBasedRenderer(symbol)
        root_rule = renderer.rootRule()

        # Index contour (every 5th interval)
        index_rule = root_rule.children()[0]
        index_rule.setLabel('Index Contour')
        index_rule.setFilterExpression(f'"ELEV" % {interval * 5} = 0')
        index_rule.symbol().setColor(color)
        index_rule.symbol().setWidth(0.5)

        # Normal contour
        normal_rule = root_rule.children()[0].clone()
        normal_rule.setLabel('Normal Contour')
        normal_rule.setFilterExpression('ELSE')
        normal_rule.symbol().setColor(color)
        normal_rule.symbol().setWidth(0.25)
        root_rule.appendChild(normal_rule)

        layer.setRenderer(renderer)
        layer.triggerRepaint()

        # ------------------------------------------------------------------ #
        # Apply labels: elevation shown on index contours only               #
        # ------------------------------------------------------------------ #
        mask = QgsTextMaskSettings()
        mask.setSize(2)
        index_contour_rule = root_rule.children()[0]
        if Qgis.QGIS_VERSION_INT < 33000:
            mask.setMaskedSymbolLayers([QgsSymbolLayerReference(
                layer.id(), QgsSymbolLayerId(index_contour_rule.ruleKey(), 0))])
        else:
            mask.setMaskedSymbolLayers([QgsSymbolLayerReference(
                layer.id(), index_contour_rule.symbol().symbolLayer(0).id())])
        mask.setEnabled(True)

        text_format = QgsTextFormat()
        text_format.setSize(10)
        text_format.setColor(color)
        text_format.setMask(mask)

        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = (
            f'CASE WHEN "ELEV" % {interval * 5} = 0 THEN "ELEV" ELSE \'\' END')
        label_settings.enabled = True
        label_settings.drawLabels = True
        label_settings.repeatDistance = 50
        label_settings.isExpression = True

        if Qgis.QGIS_VERSION_INT >= 40000:
            label_settings.placement = Qgis.LabelPlacementMode.Line
            label_settings.placementFlags = Qgis.LabelLinePlacementFlag.OnLine
        else:
            label_settings.placement = QgsPalLayerSettings.Line
            label_settings.placementFlags = QgsPalLayerSettings.OnLine

        label_settings.setFormat(text_format)

        layer.setLabelsEnabled(True)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
        layer.triggerRepaint()

        self.progress += 1
        feedback.setProgress(int(self.progress * self.status_total))

        feedback.pushInfo('\nDone.')
        QgsProject.instance().addMapLayer(layer)
        return {}

    def _smooth_terrain(self, smoothing, feedback):
        """Apply Gaussian-weighted terrain smoothing guided by TPI.

        Smoothing levels:
          - None:   no smoothing applied
          - Low:    3x3 kernel on valleys only
          - Medium: blend of 3x3 and 7x7 kernels guided by TPI
          - High:   blend of 3x3 and 13x13 kernels guided by TPI
        """
        if smoothing == 'None':
            return

        feedback.pushInfo('\nApplying terrain smoothing: ' + smoothing)

        input_dem = os.path.join(self.temp_dir, 'merged.tif')
        path = self.temp_dir

        # Convert to Float32 with nodata = -32768
        gdal.Translate(
            os.path.join(path, 'dem.tif'),
            input_dem,
            options='-ot Float32 -a_nodata -32768')

        # Build 3x3 Gaussian blur VRT
        gdal.BuildVRT(os.path.join(path, 'dem_blur_3x3.vrt'),
                      os.path.join(path, 'dem.tif'))
        with open(os.path.join(path, 'dem_blur_3x3.vrt'), 'rt') as f:
            data = f.read()
        data = data.replace('ComplexSource', 'KernelFilteredSource')
        data = data.replace(
            '<NODATA>-32768</NODATA>',
            '<NODATA>-32768</NODATA>'
            '<Kernel normalized="1"><Size>3</Size>'
            '<Coefs>0.077847 0.123317 0.077847 '
            '0.123317 0.195346 0.123317 '
            '0.077847 0.123317 0.077847</Coefs></Kernel>')
        with open(os.path.join(path, 'dem_blur_3x3.vrt'), 'wt') as f:
            f.write(data)

        feedback.setProgress(int((self.progress + 0.2) * self.status_total))

        # Compute TPI and reclassify (keep only positive values)
        gdal.DEMProcessing(
            destName=os.path.join(path, 'dem_tpi.tif'),
            srcDS=input_dem,
            processing='TPI')
        Calc(
            calc='((-1)*A*(A<0))+(A*(A>=0))',
            A=os.path.join(path, 'dem_tpi.tif'),
            outfile=os.path.join(path, 'tpi_pos.tif'),
            NoDataValue=-32768,
            overwrite=True)

        feedback.setProgress(int((self.progress + 0.4) * self.status_total))

        # Build 9x9 Gaussian blur VRT for TPI
        gdal.BuildVRT(os.path.join(path, 'tpi_blur_3x3.vrt'),
                      os.path.join(path, 'tpi_pos.tif'))
        with open(os.path.join(path, 'tpi_blur_3x3.vrt'), 'rt') as f:
            data = f.read()
        data = data.replace('ComplexSource', 'KernelFilteredSource')
        data = data.replace(
            '<NODATA>-32768</NODATA>',
            '<NODATA>-32768</NODATA>'
            '<Kernel normalized="1"><Size>9</Size>'
            '<Coefs>'
            '0 0.000001 0.000014 0.000055 0.000088 0.000055 0.000014 0.000001 0 '
            '0.000001 0.000036 0.000362 0.001445 0.002289 0.001445 0.000362 0.000036 0.000001 '
            '0.000014 0.000362 0.003672 0.014648 0.023205 0.014648 0.003672 0.000362 0.000014 '
            '0.000055 0.001445 0.014648 0.058434 0.092566 0.058434 0.014648 0.001445 0.000055 '
            '0.000088 0.002289 0.023205 0.092566 0.146634 0.092566 0.023205 0.002289 0.000088 '
            '0.000055 0.001445 0.014648 0.058434 0.092566 0.058434 0.014648 0.001445 0.000055 '
            '0.000014 0.000362 0.003672 0.014648 0.023205 0.014648 0.003672 0.000362 0.000014 '
            '0.000001 0.000036 0.000362 0.001445 0.002289 0.001445 0.000362 0.000036 0.000001 '
            '0 0.000001 0.000014 0.000055 0.000088 0.000055 0.000014 0.000001 0'
            '</Coefs></Kernel>')
        with open(os.path.join(path, 'tpi_blur_3x3.vrt'), 'wt') as f:
            f.write(data)

        feedback.setProgress(int((self.progress + 0.6) * self.status_total))

        # Normalise TPI to [0, 1]
        vrt_path = os.path.join(path, 'tpi_blur_3x3.vrt')
        if not os.path.exists(vrt_path):
            raise FileNotFoundError('File not found: ' + vrt_path)
        info = gdal.Info(ds=vrt_path, options='-hist -stats')
        try:
            max_val = re.findall(
                r'[0-9]*\.[0-9]*',
                re.findall(r'STATISTICS_MAXIMUM=\d*\.\d*', info)[0])[0]
            Calc(
                calc=f'A / {max_val}',
                A=vrt_path,
                outfile=os.path.join(path, 'tpi_norm.tif'),
                NoDataValue=-32768,
                overwrite=True)
        except Exception:
            gdal.Translate(
                destName=os.path.join(path, 'tpi_norm.tif'),
                srcDS=vrt_path)

        feedback.setProgress(int((self.progress + 0.8) * self.status_total))

        # Blend DEM with Gaussian-smoothed versions, weighted by TPI
        if smoothing == 'Low':
            Calc(
                calc='A*B+(1-A)*C',
                A=os.path.join(path, 'tpi_norm.tif'),
                B=os.path.join(path, 'dem_blur_3x3.vrt'),
                C=os.path.join(path, 'dem_blur_3x3.vrt'),
                outfile=os.path.join(path, 'merged.tif'),
                overwrite=True)

        elif smoothing == 'Medium':
            gdal.BuildVRT(os.path.join(path, 'dem_blur_7x7.vrt'),
                          os.path.join(path, 'dem.tif'))
            with open(os.path.join(path, 'dem_blur_7x7.vrt'), 'rt') as f:
                data = f.read()
            data = data.replace('ComplexSource', 'KernelFilteredSource')
            data = data.replace(
                '<NODATA>-32768</NODATA>',
                '<NODATA>-32768</NODATA>'
                '<Kernel normalized="1"><Size>7</Size>'
                '<Coefs>'
                '0.000036 0.000363 0.001446 0.002291 0.001446 0.000363 0.000036 '
                '0.000363 0.003676 0.014662 0.023226 0.014662 0.003676 0.000363 '
                '0.001446 0.014662 0.058488 0.092651 0.058488 0.014662 0.001446 '
                '0.002291 0.023226 0.092651 0.146768 0.092651 0.023226 0.002291 '
                '0.001446 0.014662 0.058488 0.092651 0.058488 0.014662 0.001446 '
                '0.000363 0.003676 0.014662 0.023226 0.014662 0.003676 0.000363 '
                '0.000036 0.000363 0.001446 0.002291 0.001446 0.000363 0.000036'
                '</Coefs></Kernel>')
            with open(os.path.join(path, 'dem_blur_7x7.vrt'), 'wt') as f:
                f.write(data)
            Calc(
                calc='A*B+(1-A)*C',
                A=os.path.join(path, 'tpi_norm.tif'),
                B=os.path.join(path, 'dem_blur_3x3.vrt'),
                C=os.path.join(path, 'dem_blur_7x7.vrt'),
                outfile=os.path.join(path, 'merged.tif'),
                overwrite=True)

        else:  # High
            gdal.BuildVRT(os.path.join(path, 'dem_blur_13x13.vrt'),
                          os.path.join(path, 'dem.tif'))
            with open(os.path.join(path, 'dem_blur_13x13.vrt'), 'rt') as f:
                data = f.read()
            data = data.replace('ComplexSource', 'KernelFilteredSource')
            data = data.replace(
                '<NODATA>-32768</NODATA>',
                '<NODATA>-32768</NODATA>'
                '<Kernel normalized="1"><Size>13</Size>'
                '<Coefs>'
                '0 0 0 0 0 0 0 0 0 0 0 0 0 '
                '0 0 0 0 0 0.000001 0.000001 0.000001 0 0 0 0 '
                '0 0 0 0 0.000001 0.000014 0.000055 0.000088 0.000055 0.000014 0.000001 0 0 '
                '0 0 0.000014 0.000362 0.003672 0.014648 0.023204 0.014648 0.003672 0.000362 0.000014 0 0 '
                '0 0.000001 0.000055 0.001445 0.014648 0.058433 0.092564 0.058433 0.014648 0.001445 0.000055 0.000001 0 '
                '0 0.000001 0.000088 0.002289 0.023204 0.092564 0.146632 0.092564 0.023204 0.002289 0.000088 0.000001 0 '
                '0 0.000001 0.000055 0.001445 0.014648 0.058433 0.092564 0.058433 0.014648 0.001445 0.000055 0.000001 0 '
                '0 0 0.000014 0.000362 0.003672 0.014648 0.023204 0.014648 0.003672 0.000362 0.000014 0 0 '
                '0 0 0 0.000001 0.000036 0.000362 0.001445 0.002289 0.001445 0.000362 0.000036 0.000001 0 '
                '0 0 0 0 0.000001 0.000014 0.000055 0.000088 0.000055 0.000014 0.000001 0 0 '
                '0 0 0 0 0 0.000001 0.000001 0.000001 0 0 0 0 0 '
                '0 0 0 0 0 0 0 0 0 0 0 0 0'
                '</Coefs></Kernel>')
            with open(os.path.join(path, 'dem_blur_13x13.vrt'), 'wt') as f:
                f.write(data)
            Calc(
                calc='A*B+(1-A)*C',
                A=os.path.join(path, 'tpi_norm.tif'),
                B=os.path.join(path, 'dem_blur_3x3.vrt'),
                C=os.path.join(path, 'dem_blur_13x13.vrt'),
                outfile=os.path.join(path, 'merged.tif'),
                overwrite=True)

        feedback.setProgress(int((self.progress + 1.0) * self.status_total))

    def icon(self):
        cmd_folder = os.path.dirname(__file__)
        return QIcon(os.path.join(cmd_folder, 'logo.png'))

    def name(self):
        return 'Contour Lines'

    def displayName(self):
        return self.tr(self.name())

    def group(self):
        return self.tr(self.groupId())

    def groupId(self):
        return ''

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ContourLinesAlgorithm()
