# ---------------------------------------------------------------------------------------------
#
#  aggregate_ecostress.py
#
#  Author:  Todd Berendes, UAH ITSC, April 2021
#
#  Description: This program reads ECOSTRESS geotiff files (one channel) and aggregates
#    the values into organizational units defined in the geojson input configuration file.
#    The python script calls gdal which  must be installed as a package in the operating system.
#
#  Syntax: currently no input parameters
#
#  To Do: modify to accept input parameters
#
# ---------------------------------------------------------------------------------------------
import os
import sys
import statistics
import json
#from urllib.parse import unquote_plus, urlparse, urljoin
#import datetime

#import rasterio
#import numpy as np
#from affine import Affine
#from pyproj import Proj, transform
#import gdal
from osgeo import gdal, gdal_array

from matplotlib.patches import Polygon
import matplotlib.path as mpltPath
import numpy
import ephem

def daytime(lat, long, time):
   o = ephem.Observer()
   o.long = long
   o.lat = lat
   o.date = time
   s = ephem.Sun()
   s.compute(o)
   return s.alt > 0

def accumVariableByDistrict(polylist, variable, lat, lon, districtVariable,
                            minlat, minlon, maxlat, maxlon, valid_min, valid_max):

    for poly in polylist:
        if poly.get_label() not in districtVariable.keys():
            districtVariable[poly.get_label()] = []

    for i in range(lat.shape[0]):
        for j in range(lat.shape[1]):
            # mask is not reliable, used for NDVI, but not for LST, for now we will not use it
            #if not mask[i][j]:
            # if mask[i][j]:
            #     continue
            if lon[i][j] < minlon or lon[i][j] > maxlon:
                continue
            #            print("i ",i)
            if lat[i][j] < minlat or lat[i][j] > maxlat:
                continue
            #                print("j ",j)
            #                print("lat ", lat[i], " lon ", lon[j], " poly ", poly.get_label())
            if variable[i][j] < valid_min or variable[i][j] > valid_max:
                continue
            for poly in polylist:
                path = mpltPath.Path(poly.xy)
                inside = path.contains_point((lon[i][j], lat[i][j]))
                if inside:
                    # add Variable value to district
                    # need to change this to check against a fill value
                    #if variable[i][j] >= valid_min and variable[i][j] <= valid_max:
                    districtVariable[poly.get_label()].append(float(variable[i][j]))
                    # values of zero or below are missing, cloud contamination in 8day composite, do not use
                    # else:
                    #     districtVariable[poly.get_label()].append(0.0)
                    break # only allow membership in one polygon, doesn't allow for overlapping regions

#                    im.putpixel((i,height-1-j),(r, g, b))
#                    print("lat ", lat[j], " lon ", lon[i], " variable ", variable[i][j], " inside ", poly.get_label())
    return

def calcDistrictStats(districtVariable):
    districtVariableStats = {}
    for dist in districtVariable.keys():
        if dist not in districtVariableStats.keys():
            districtVariableStats[dist] = {}
        if len(districtVariable[dist]) > 0:
            #            print('len ',len(districtVariable[dist]))
            #            print('points ',districtVariable[dist])
            mean = statistics.mean(districtVariable[dist])
            median = statistics.median(districtVariable[dist])
            maxval = max(districtVariable[dist])
            minval = min(districtVariable[dist])
        else:
            mean = -9999.0
            median = -9999.0
            maxval = -9999.0
            minval = -9999.0
        #        meadian_high = statistics.median_high(districtVariable[dist])
        #        meadian_low = statistics.median_low(districtVariable[dist])
        #        std_dev = statistics.stdev(districtVariable[dist])
        #        variance = statistics.variance(districtVariable[dist])
        districtVariableStats[dist] = dict([
            ('mean', mean),
            ('median', median),
            ('max', maxval),
            ('min', minval),
            ('count', len(districtVariable[dist]))
        ])
    return districtVariableStats

def find_maxmin_latlon(lat,lon,minlat,minlon,maxlat,maxlon):
    if lat > maxlat:
        maxlat = lat
    if lat < minlat:
        minlat = lat
    if lon > maxlon:
        maxlon = lon
    if lon < minlon:
        minlon = lon
    return minlat,minlon,maxlat,maxlon

def process_file(filename, districts, dataElementDay, dataElementNight, statType, centerLat, centerLon):
    print('filename ' + filename)
#    with gzip.open(filename) as gz:
#        with NetCDFFile('dummy', mode='r', memory=gz.read()) as nc:
   # dictionaries for computing stats by district
    districtVariable = {}
    #districtVariableStats = {}
    #districtPolygons = {}

    dateStr = ""

    # Open tif file
    if '.gz' in filename: # compressed gzip file
        ds = gdal.Open("/vsigzip/"+filename)
    else:
        ds = gdal.Open(filename)
    #raster = ds.GetRasterBand(1)

    valid_min=227
    valid_max=330
    #valid_min=1
    #valid_max=100000
    # valid_min=raster.GetMinimum()
    # valid_max=raster.GetMaximum()
    print("valid_min ", valid_min)
    print("valid_max ", valid_max)

    # GDAL affine transform parameters, According to gdal documentation xoff/yoff are image left corner, a/e are pixel wight/height and b/d is rotation and is zero if image is north up.
    xoff, a, b, yoff, d, e = ds.GetGeoTransform()

    def pixel2coord(x, y):
        """Returns global coordinates from pixel x, y coords"""
        xp = a * x + b * y + xoff
        yp = d * x + e * y + yoff
        return (xp, yp)

    # get columns and rows of your image from gdalinfo
    cols = ds.RasterXSize
    rows = ds.RasterYSize

    lon = numpy.zeros(shape=(rows,cols))
    lat = numpy.zeros(shape=(rows,cols))

    #variable = ds.ReadAsArray(0, 0, cols, rows).astype(numpy.float)
    # oddly, "variable" is accessed as [row][col], i.e. [Y][X], so set up lat, lon using same dimensions
#    variable = ds.ReadAsArray(0, 0, cols, rows).astype(float)
    variable = ds.ReadAsArray(0, 0, cols, rows).astype(numpy.float64)
    for row in range(0, rows):
        for col in range(0, cols):
            lon[row][col], lat[row][col] = pixel2coord(col, row)

    # # Read raster
    # with rasterio.open(filename) as r:
    #     T0 = r.transform  # upper-left pixel corner affine transform
    #     p1 = Proj(r.crs)
    #     variable = r.read()  # pixel values
    #
    # # All rows and columns
    # cols, rows = np.meshgrid(np.arange(variable.shape[2]), np.arange(variable.shape[1]))
    #
    # # Get affine transform for pixel centres
    # T1 = T0 * Affine.translation(0.5, 0.5)
    # # Function to convert pixel row/column index (from 0) to easting/northing at centre
    # rc2en = lambda r, c: (c, r) * T1
    #
    # # All eastings and northings (there is probably a faster way to do this)
    # eastings, northings = np.vectorize(rc2en, otypes=[np.float, np.float])(rows, cols)
    #
    # # Project all longitudes, latitudes
    # p2 = Proj(proj='latlong', datum='WGS84')
    # lon, lat = transform(p1, p2, eastings, northings)


#   lat = nc.variables['Latitude'][:]
#    lon = nc.variables['Longitude'][:]

    print("lat ", lat[0][0], "lon", lon[0][0])
    print("lat.shape[0]", lat.shape[0])
    print("lat.shape[1]", lat.shape[1])

    #daytime("53", "-2", '2018/02/08 16:30:00')

    # filename format:  ECOSTRESS_L2_LSTE_09009_009_20200206T214458_0601_01_LST_GEO.tif
    # parse out date/time from filename
    # strip out yyyyddd from opendap url
    if "Clipped_".lower() in filename.lower():
        tempstr = os.path.basename(filename).split("_")[6]
    else:
        tempstr = os.path.basename(filename).split("_")[5]
    year = tempstr[0:4]
    print("year ", year)
    month = tempstr[4:6]
    print("month ", month)
    day = tempstr[6:8]
    print("day ", day)
    dateStr = year + month +day
    print("date ", dateStr)
    hour=tempstr[9:11]
    min=tempstr[11:13]
    sec=tempstr[13:15]
    timestr= hour+":"+min+":"+sec
    print("time ", timestr)

    timestamp = year+"/"+month+"/"+day+" "+timestr
    print("timestamp",timestamp)

    #dayFlag = daytime(centerLat, centerLon, '2018/02/08 16:30:00')
    dayFlag = daytime(centerLat, centerLon, timestamp)
    print("daytime flag ",dayFlag)

    #    im = PIL.Image.new(mode="RGB", size=(lon.shape[0], lat.shape[0]), color=(255, 255, 255))

    for district in districts:
        shape = district['geometry']
        coords = district['geometry']['coordinates']
 #       name = district['properties']['name']
        name = district['name']
        dist_id = district['id']

        print("district: " + name)
        def handle_subregion(subregion):
#            poly = Polygon(subregion, edgecolor='k', linewidth=1., zorder=2, label=name)
            poly = Polygon(subregion, edgecolor='k', linewidth=1., zorder=2, label=dist_id)
            return poly

        distPoly = []

        minlat = 90.0
        maxlat = -90.0
        minlon = 180.0
        maxlon = -180.0
        if shape["type"] == "Polygon":
            for subregion in coords:
                distPoly.append(handle_subregion(subregion))
                for coord in subregion:
                    minlat, minlon, maxlat, maxlon = find_maxmin_latlon(coord[1], coord[0], minlat, minlon, maxlat, maxlon)
        elif shape["type"] == "MultiPolygon":
            for subregion in coords:
                #            print("subregion")
                for sub1 in subregion:
                    #                print("sub-subregion")
                    distPoly.append(handle_subregion(sub1))
                    for coord in sub1:
                        minlat, minlon, maxlat, maxlon = find_maxmin_latlon(coord[1], coord[0], minlat, minlon,
                                                                        maxlat, maxlon)
        else:
            print
            "Skipping", dist_id, \
            "because of unknown type", shape["type"]
        # compute statisics
#        accumVariableByDistrict(distPoly, variable, lat, lon, districtVariable,minlat,minlon,maxlat,maxlon,im)
        accumVariableByDistrict(distPoly, variable, lat, lon,
                                districtVariable,minlat,minlon,maxlat,maxlon,
                                valid_min, valid_max)
        #districtPolygons[dist_id] = distPol

    # reformat new json structure
#    outputJson = {'dataValues' : []}
    districtVariableStats = calcDistrictStats(districtVariable)
    for district in districts:
       # name = district['properties']['name']
        dist_id = district['id']
        name = district['name']
        print("district name ", name)
        print("district id", dist_id)
        print("mean Variable ", districtVariableStats[dist_id]['mean'])
        print("median Variable ", districtVariableStats[dist_id]['median'])
        print("max Variable ", districtVariableStats[dist_id]['max'])
        print("min Variable ", districtVariableStats[dist_id]['min'])
        print("count ", districtVariableStats[dist_id]['count'])
    outputJson = []
    for key in districtVariableStats.keys():
        value = districtVariableStats[key][statType]
        if dayFlag:
            #jsonRecord = {'dataElement':dataElementDay,'period':dateStr,'orgUnit':key,'value':value}
            if value > 0:
                jsonRecord = {'dataElement':dataElementDay,'period':dateStr,'orgUnit':key,'value':value-273.15}
                outputJson.append(jsonRecord)
        else:
            #jsonRecord = {'dataElement': dataElementNight, 'period': dateStr, 'orgUnit': key, 'value': value}'
            if value > 0:
                jsonRecord = {'dataElement': dataElementNight, 'period': dateStr, 'orgUnit': key, 'value': value-273.15}
                outputJson.append(jsonRecord)

    return outputJson, dayFlag

def main():

    ECO_DATA_DIR = '/media/sf_tberendes/ecostress/data_all'
    OUT_DIR = '/media/sf_tberendes/ecostress/upload_all'
#    ECO_DATA_DIR = '/media/sf_tberendes/ecostress/data_3_7_22'
#    OUT_DIR = '/media/sf_tberendes/ecostress/upload_3_7_22'
#    ECO_DATA_DIR = '/media/sf_tberendes/ecostress/data'
#    OUT_DIR = '/media/sf_tberendes/ecostress/upload'
    CONFIG_FILE = '/media/sf_tberendes/ecostress/config/ecostress_geo_config.json'
#    CONFIG_FILE = '/media/sf_tberendes/ecostress/config/ecostress_geo_config_day.json'
#    CONFIG_FILE = '/media/sf_tberendes/ecostress/config/ecostress_geo_config_night.json'
    # center lat/lon for sierra leon used in pyephem to find day/night,
    # NOTE these must be strings NOT floats
    centerLat = '8.5'
    centerLon = '-11.75'

    input_json = {"message": "error"}
    try:
        with open(CONFIG_FILE) as f:
            input_json = json.load(f)
        f.close()
    except IOError:
        print("Could not read file:" + CONFIG_FILE)
        sys.exit(1)

    #outputJson = {'dataValues' : []}
    outputJsonDay = {'dataValues' : []}
    outputJsonNight = {'dataValues' : []}

    fileJson={}
    for root, dirs, files in os.walk(ECO_DATA_DIR, topdown=False):
        for file in files:
            print('file ' + file)
            # only process the original staged files until new ones are fixed:
            #*************************^&%&^%^$^%$#%#%$#%$#%$#%$#%$#%$ remove this!!!!!!!!!!!!!!!!!
#            if file.startswith('ECO'):
#                continue
            if file.endswith('.tif') or file.endswith('.tif.gz'):
                #if json file for this image already exists, read it and append to upload files
                if os.path.isfile(OUT_DIR + "/"+file+".json"):
                    with open(OUT_DIR + "/"+file+".json") as f:
                        fileJson = json.load(f)
                        records = fileJson['records']
                        dayFlag = fileJson['daytime']

                    # this block is a fix for bad day/night flag, remove when fixed
                    # tempstr = os.path.basename(file).split("_")[5]
                    # year = tempstr[0:4]
                    # print("year ", year)
                    # month = tempstr[4:6]
                    # print("month ", month)
                    # day = tempstr[6:8]
                    # print("day ", day)
                    # dateStr = year + month + day
                    # print("date ", dateStr)
                    # hour = tempstr[9:11]
                    # min = tempstr[11:13]
                    # sec = tempstr[13:15]
                    # timestr = hour + ":" + min + ":" + sec
                    # print("time ", timestr)
                    #
                    # timestamp = year + "/" + month + "/" + day + " " + timestr
                    # print("timestamp", timestamp)
                    #
                    # # dayFlag = daytime(centerLat, centerLon, '2018/02/08 16:30:00')
                    # dayFlag = daytime(centerLat, centerLon, timestamp)
                    # print("daytime flag ", dayFlag)
                    # fileJson['daytime'] = dayFlag
                    # with open(OUT_DIR + "/"+file+".json", 'w') as json_file:
                    #     json.dump(fileJson, json_file)
                else:
                    records, dayFlag = process_file(os.path.join(root, file), input_json['boundaries'], input_json['data_element_id_day'],
                                        input_json['data_element_id_night'],input_json['stat_type'], centerLat, centerLon)
                    fileJson['daytime'] = dayFlag
                    fileJson['records'] = records
                    # write out results for individual file, can be used to create final file if interrupted
                    with open(OUT_DIR + "/"+file+".json", 'w') as json_file:
                        json.dump(fileJson, json_file)
            # construct output filename based on date and variable
            for record in records:
                # ignore data element ids in origninal files, use config version
                if fileJson['daytime']:
                    record['dataElement'] = input_json['data_element_id_day']
                else:
                    record['dataElement'] = input_json['data_element_id_night']
                if record['value'] >0.0:
                    # if value > 100, assume in Kelvin, convert to Celsius
#                    if record['value'] >100.0:
#                        record['value'] = record['value'] - 273.15
                    # outputJson['dataValues'].append(record)
                    if dayFlag:
                        outputJsonDay['dataValues'].append(record)
                    else:
                        outputJsonNight['dataValues'].append(record)

    #    with open(OUT_DIR+ "/" + file.split('.')[0]+'.json', 'w') as result_file:
    # write out accumulated results for all files
    # with open(OUT_DIR + "/ecostress_lst_upload.json", 'w') as result_file:
    #     json.dump(outputJson, result_file)
    with open(OUT_DIR + "/ecostress_lst_day_upload.json", 'w') as result_file:
        json.dump(outputJsonDay, result_file)
    with open(OUT_DIR + "/ecostress_lst_night_upload.json", 'w') as result_file:
        json.dump(outputJsonNight, result_file)

if __name__ == '__main__':
   main()
# from Navaneeth, 4/7/21 regarding new AWS instance
# Data element ID for the Ecostress LST: tgOFXbBbJDk