# Contour Lines — QGIS Plugin

A QGIS Processing plugin that generates contour lines anywhere in the world using the **Copernicus GLO-30 Digital Elevation Model (DEM)** provided free of charge by the European Space Agency (ESA).

---

## Features

- Worldwide coverage (~30 m / 1 arc-second resolution)
- No API key, no account, no registration required
- DEM tiles are downloaded on demand and cached locally for reuse
- Adjustable contour interval (1–1000 m)
- Four terrain smoothing levels (None / Low / Medium / High)
- Rule-based symbology: index contours (every 5th interval) with labels, normal contours
- Automatic reprojection to the current QGIS project CRS
- Optional proxy authentication support

---

## Data Source

Elevation data is sourced from the **Copernicus GLO-30 Public DEM** hosted on AWS Open Data:

- Registry: https://registry.opendata.aws/copernicus-dem/
- Documentation: https://copernicus-dem-30m.s3.amazonaws.com/readme.html

**Attribution:**  
Copernicus DEM © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.

**Licence:**  
GLO-30 Public is available free of charge for any use under the terms of the [Copernicus DEM licence](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).

> **Note:** A small number of tiles covering specific countries are withheld from the public release by the Copernicus Programme. If a tile is unavailable, the plugin logs a warning and continues processing with the remaining tiles. The full list of withheld tiles is published [here](https://spacedata.copernicus.eu/documents/20123/121239/Non-released-tiles_GLO-30_PUBLIC_Dec+%282%29.xlsx). Ocean tiles are also absent (elevation is assumed to be zero for those areas).

---

## Installation

1. Download or clone this repository.
2. Copy the `ContourLines` folder to your QGIS user plugins directory:
   - **macOS/Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Restart QGIS and enable the plugin in **Plugins → Manage and Install Plugins**.

---

## Usage

1. Open the **Processing Toolbox** (`Ctrl+Alt+T`).
2. Navigate to **Contour Lines → Contour Lines**.
3. Configure the parameters:
   - **Area of Interest:** Draw or select an extent on the map.
   - **Contour interval:** Vertical spacing between contour lines in metres (default: 10 m).
   - **Terrain smoothing level:** Controls how much the DEM is smoothed before contouring. Higher smoothing reduces noise at the cost of fine topographic detail.
   - **Contour line colour:** Choose the colour and opacity for the output layer.
   - **Proxy authentication:** Optional — configure only if your network requires a proxy.
4. Click **Run**. The plugin will download the required tiles, merge them, apply smoothing, generate contours and add the resulting layer to the map.

### Caching

Downloaded DEM tiles are stored in a local cache folder (`ContourLines/` inside your OS temp directory). Subsequent runs over overlapping areas skip the download and use the cached files directly.

---

## Requirements

- QGIS 3.16 or later
- Internet connection (for tile downloads)
- GDAL (bundled with QGIS)

---

## Relationship to CurvaDeNivel

This plugin is a worldwide successor to [CurvaDeNivel](https://github.com/DanielHSMartin/CurvaDeNivel), which generates contour lines over Brazil using INPE TOPODATA data. The core processing pipeline (smoothing algorithm, contour generation, symbology) is identical; the data source and tile grid logic have been updated for global coverage.

---

## Licence

This plugin is released under the **GNU General Public License v2 or later**. See [LICENSE](LICENSE) for details.

---

## Author

Daniel Hulshof Saint Martin  
daniel.hulshof@gmail.com
