"""Calculates mean temperature for plots in georeferenced IR images
"""

import argparse
import datetime
import json
import logging
import os
import dateutil.parser
import yaml
import numpy as np
from osgeo import ogr
import osr

from terrautils.betydb import get_site_boundaries
from terrautils.spatial import geojson_to_tuples_betydb, find_plots_intersect_boundingbox, \
     clip_raster, convert_json_geometry, geometry_to_geojson, centroid_from_geojson
from terrautils.imagefile import image_get_geobounds, get_epsg
import terrautils.lemnatec

import transformer_class
import configuration

terrautils.lemnatec.SENSOR_METADATA_CACHE = os.path.dirname(os.path.realpath(__file__))

# The image file name extensions we support
SUPPORTED_IMAGE_EXTS = [".tif", ".tiff"]

# Array of trait names that should have array values associated with them
TRAIT_NAME_ARRAY_VALUE = ['surface_temperature', 'site']

# Mapping of default trait names to fixed values
TRAIT_NAME_MAP = {
    'access_level': '2',
    'citation_author': '',
    'citation_year': '',
    'citation_title': '',
    'method': 'Mean temperature from infrared images'
}

def get_fields() -> list:
    """Returns the supported field names as a list
    """
    return ['local_datetime', 'surface_temperature', 'access_level', 'site',
            'citation_author', 'citation_year', 'citation_title', 'method']

def get_default_trait(trait_name: str):
    """Returns the default value for the trait name
    Args:
       trait_name(str): the name of the trait to return the default value for
    Return:
        If the default value for a trait is configured, that value is returned. Otherwise
        an empty string is returned.
    """
    # pylint: disable=global-statement
    global TRAIT_NAME_ARRAY_VALUE
    global TRAIT_NAME_MAP

    if trait_name in TRAIT_NAME_ARRAY_VALUE:
        return []   # Return an empty list when the name matches
    if trait_name in TRAIT_NAME_MAP:
        return TRAIT_NAME_MAP[trait_name]

    return ""

def get_traits_table() -> list:
    """Returns the field names and default trait values

    Returns:
        A tuple containing the list of field names and a dictionary of default field values
    """
    # Compiled traits table
    fields = get_fields()
    traits = {}
    for field_name in fields:
        traits[field_name] = get_default_trait(field_name)

    return [fields, traits]

def generate_traits_list(traits: list) -> list:
    """Returns an array of trait values

    Args:
        traits(dict): contains the set of trait values to return

    Return:
        Returns an array of trait values taken from the traits parameter
    """
    # compose the summary traits
    fields = get_fields()
    trait_list = []
    for field_name in fields:
        if field_name in traits:
            trait_list.append(traits[field_name])
        else:
            trait_list.append(get_default_trait(field_name))

    return trait_list

def get_image_bounds(image_file: str) -> str:
    """Loads the boundaries from an image file
    Arguments:
        image_file: path to the image to load the bounds from
    Return:
        Returns the GEOJSON of the bounds if they could be loaded and converted (if necessary).
        None is returned if the bounds are loaded or can't be converted
    """
    # If the file has a geo shape we store it for clipping
    bounds = image_get_geobounds(image_file)
    epsg = get_epsg(image_file)
    if bounds[0] != np.nan:
        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(bounds[2], bounds[1])     # Upper left
        ring.AddPoint(bounds[3], bounds[1])     # Upper right
        ring.AddPoint(bounds[3], bounds[0])     # lower right
        ring.AddPoint(bounds[2], bounds[0])     # lower left
        ring.AddPoint(bounds[2], bounds[1])     # Closing the polygon

        poly = ogr.Geometry(ogr.wkbPolygon)
        poly.AddGeometry(ring)

        ref_sys = osr.SpatialReference()
        if ref_sys.ImportFromEPSG(int(epsg)) == ogr.OGRERR_NONE:
            poly.AssignSpatialReference(ref_sys)
            return geometry_to_geojson(poly)

        logging.warning("Failed to import EPSG %s for image file %s", str(epsg), image_file)

    return None

def get_spatial_reference_from_json(geojson: str):
    """Returns the spatial reference embedded in the geojson.
    Args:
        geojson(str): the geojson to get the spatial reference from
    Return:
        The osr.SpatialReference that represents the geographical coordinate system
        in the geojson. None is returned if a spatial reference isn't found
    """
    yaml_geom = yaml.safe_load(geojson)
    current_geom = ogr.CreateGeometryFromJson(json.dumps(yaml_geom))

    if current_geom:
        return current_geom.GetSpatialReference()

    raise RuntimeError("Specified JSON does not have a valid sptial reference")

def add_parameters(parser: argparse.ArgumentParser) -> None:
    """Adds parameters
    Arguments:
        parser: instance of argparse
    """
    parser.add_argument('--citation_author', dest="citationAuthor", type=str, nargs='?',
                        default="Unknown",
                        help="author of citation to use when generating measurements")

    parser.add_argument('--citation_title', dest="citationTitle", type=str, nargs='?',
                        default="Unknown",
                        help="title of the citation to use when generating measurements")

    parser.add_argument('--citation_year', dest="citationYear", type=str, nargs='?',
                        default="Unknown",
                        help="year of citation to use when generating measurements")

def check_continue(transformer: transformer_class.Transformer, check_md: dict, transformer_md: dict, full_md: dict) -> tuple:
    """Checks if conditions are right for continuing processing
    Arguments:
        transformer: instance of transformer class
    Return:
        Returns a tuple containing the return code for continuing or not, and
        an error message if there's an error
    """
    # pylint: disable=unused-argument
    # Check that we have what we need
    if 'list_files' not in check_md:
        return -1, "Unable to find list of files associated with this request"

    # Make sure there's a tiff file to process
    image_exts = SUPPORTED_IMAGE_EXTS
    found_file = False
    for one_file in check_md['list_files']():
        ext = os.path.splitext(one_file)[1]
        if ext and ext in image_exts:
            found_file = True
            break

    # Return the appropriate result
    return 0 if found_file else (-1, "Unable to find an image file to work with")

def perform_process(transformer: transformer_class.Transformer, check_md: dict, transformer_md: list, full_md: list) -> dict:
    """Performs the processing of the data
    Arguments:
        transformer: instance of transformer class
    Return:
        Returns a dictionary with the results of processing
    """
    # pylint: disable=unused-argument
    # Disabling pylint checks because resolving them would make code unreadable
    # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    # Setup local variables
    start_timestamp = datetime.datetime.now()
    timestamp = dateutil.parser.parse(check_md['timestamp'])
    datestamp = timestamp.strftime("%Y-%m-%d")
    localtime = timestamp.strftime("%Y-%m-%dT%H:%M:%S")

    geo_csv_filename = os.path.join(check_md['working_folder'], "meantemp_geostreams.csv")
    bety_csv_filename = os.path.join(check_md['working_folder'], "meantemp.csv")
    geo_file = open(geo_csv_filename, 'w')
    bety_file = open(bety_csv_filename, 'w')

    (fields, traits) = get_traits_table()

    # Setup default trait values
    if transformer.args.citationAuthor is not None:
        traits['citation_author'] = transformer.args.citationAuthor
    if transformer.args.citationTitle is not None:
        traits['citation_title'] = transformer.args.citationTitle
    if transformer.args.citationYear is not None:
        traits['citation_year'] = transformer.args.citationYear
    else:
        traits['citation_year'] = timestamp.year

    geo_csv_header = ','.join(['site', 'trait', 'lat', 'lon', 'dp_time', 'source', 'value', 'timestamp'])
    bety_csv_header = ','.join(map(str, fields))
    if geo_file:
        geo_file.write(geo_csv_header + "\n")
    if bety_file:
        bety_file.write(bety_csv_header + "\n")

    all_plots = get_site_boundaries(datestamp, city='Maricopa')
    logging.debug("Found %s plots for date %s", str(len(all_plots)), str(datestamp))

    # Loop through finding all image files
    image_exts = SUPPORTED_IMAGE_EXTS
    num_files = 0
    number_empty_plots = 0
    total_plots_calculated = 0
    total_files = 0
    processed_plots = 0
    logging.debug("Looking for images with an extension of: %s", ",".join(image_exts))
    for one_file in check_md['list_files']():
        total_files += 1
        ext = os.path.splitext(one_file)[1]
        if not ext or ext not in image_exts:
            logging.debug("Skipping non-supported file '%s'", one_file)
            continue

        image_bounds = get_image_bounds(one_file)
        if not image_bounds:
            logging.info("Image file does not appear to be geo-referenced '%s'", one_file)
            continue

        overlap_plots = find_plots_intersect_boundingbox(image_bounds, all_plots, fullmac=True)
        num_plots = len(overlap_plots)

        if not num_plots or num_plots < 0:
            logging.info("No plots intersect file '%s'", one_file)
            continue

        num_files += 1
        image_spatial_ref = get_spatial_reference_from_json(image_bounds)
        for plot_name in overlap_plots:
            processed_plots += 1
            plot_bounds = convert_json_geometry(overlap_plots[plot_name], image_spatial_ref)
            tuples = geojson_to_tuples_betydb(yaml.safe_load(plot_bounds))
            centroid = json.loads(centroid_from_geojson(plot_bounds))["coordinates"]

            try:
                logging.debug("Clipping raster to plot")
                clip_path = os.path.join(check_md['working_folder'], "temp.tif")
                pxarray = clip_raster(one_file, tuples, clip_path)
                if os.path.exists(clip_path):
                    os.remove(clip_path)
                if pxarray is not None:
                    logging.debug("Calculating mean temperature")
                    pxarray[pxarray < 0] = np.nan
                    mean_tc = np.nanmean(pxarray) - 273.15

                    # Check for empty plots
                    if np.isnan(mean_tc):
                        number_empty_plots += 1
                        continue

                    # Write the data point geographically and otherwise
                    logging.debug("Writing to CSV files")
                    if geo_file:
                        csv_data = ','.join([plot_name,
                                             'IR Surface Temperature',
                                             str(centroid[1]),
                                             str(centroid[0]),
                                             localtime,
                                             one_file,
                                             str(mean_tc),
                                             datestamp])
                        geo_file.write(csv_data + "\n")

                    if bety_file:
                        traits['surface_temperature'] = str(mean_tc)
                        traits['site'] = plot_name
                        traits['local_datetime'] = localtime
                        trait_list = generate_traits_list(traits)
                        csv_data = ','.join(map(str, trait_list))
                        bety_file.write(csv_data + "\n")

                    total_plots_calculated += 1

                else:
                    continue
            except Exception as ex:
                logging.warning("Exception caught while processing mean temperature: %s", str(ex))
                logging.warning("Error generating mean temperature for '%s'", one_file)
                logging.warning("    plot name: '%s'", plot_name)
                continue

    # Check that we got something
    if not num_files:
        return {'code': -1000, 'error': "No files were processed"}
    if not total_plots_calculated:
        return {'code': -1001, 'error': "No plots intersected with the images provided"}

    # Setup the metadata for returning files
    file_md = []
    if geo_file:
        file_md.append({'path': geo_csv_filename, 'key': 'csv'})
    if bety_file:
        file_md.append({'path': bety_csv_filename, 'key': 'csv'})

    # Perform cleanup
    if geo_file:
        geo_file.close()
    if bety_file:
        bety_file.close()

    return {'code': 0,
            'files': file_md,
            configuration.TRANSFORMER_NAME:
            {
                'version': configuration.TRANSFORMER_VERSION,
                'utc_timestamp': datetime.datetime.utcnow().isoformat(),
                'processing_time': str(datetime.datetime.now() - start_timestamp),
                'total_file_count': total_files,
                'processed_file_count': num_files,
                'total_plots_processed': processed_plots,
                'empty_plots': number_empty_plots
            }
            }
