"""
Functions commonly required for cleaning input datasets
"""

import pandas as pd
from bng_latlon import OSGB36toWGS84


def filter_out_wales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter out Welsh LSOAs from the input dataframe

    Parameters:
        df (pd.DataFrame): Input dataframe with LSOA21CD field containing LSOA codes

    Returns:
        pd.DataFrame: Input dataframe with any rows containing Wales LSOA codes removed
    """
    return df[~df["LSOA21CD"].str.startswith("W")]


def OSGB_to_LatLon(x: float, y: float) -> pd.Series:
    """
    Convert OSGB36 coordinates to latitude and longitude

    Parameters:
        x (float): Easting coordinate
        y (float): Northing coordinate

    Returns:
        pd.Series: Latitude and Longitude
    """
    latlon = OSGB36toWGS84(x, y)
    lat, lon = latlon[0], latlon[1]
    return pd.Series([lat, lon])


def create_lat_lon_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create latitude and longitude columns from OSGB36 coordinates

    Parameters:
        df: pd.DataFrame: Input dataframe with columns `x` and `y`, containing OSGB36
        coordinates

    Returns:
        pd.DataFrame: Input dataframe with new `lat` and `lon` columns
    """
    df[["lat", "lon"]] = df.apply(
        lambda row: OSGB_to_LatLon(row["x"], row["y"]), axis=1
    )
    return df


def drop_locations_with_no_lat_lon(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows from the input dataframe where latitude and longitude are not available

    Parameters:
        df (pd.DataFrame): Input dataframe with `Location Latitude` and
        `Location Longitude` columns

    Returns:
        pd.DataFrame: Input dataframe with any rows containing no latitude or longitude
        values removed, and those columns renamed to `lat` and `lon`
    """
    df.dropna(subset=["lat", "lon"], inplace=True)
    return df