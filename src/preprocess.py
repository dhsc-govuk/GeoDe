"""
Functions for preprocessing data in Python, so that data containing the nearest
locations from one dataset to each locations in another dataset in England can be
used by Scala code.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import scipy as sp


def convert_lat_lon_to_km(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert latitudes and longitudes to kilometres.

    Conversion is the distance in km between two points with 1 lat/lon distance in UK
    Longitude value was 69.2km originally, changed to 67 (mid point between 63 and 70 to
    account for curvature of Earth within UK)
    https://www.omnicalculator.com/other/latitude-longitude-distance

    Parameters:
        df (pd.DataFrame): Input dataframe with `lat` and `lon` columns

    Returns:
        pd.DataFrame: Input dataframe with new `lat_adj` and `lon_adj` columns
    """
    df["lat_adj"] = df["lat"] * 111.2
    df["lon_adj"] = df["lon"] * 67
    return df


def create_dict_of_location_ids_to_coordinates(
    df: pd.DataFrame, id_column_name: str
) -> dict:
    """
    Create a dictionary of location IDs to coordinates from the input dataframe

    Parameters:
        df (pd.DataFrame): Input dataframe with `lat_adj` and `lon_adj` columns, and a
        column with the same name as `id_column_name`
        id_column_name (str): Name of the column containing location IDs

    Returns:
        dict: Dictionary of location IDs to coordinates
    """
    return dict(zip(df[id_column_name], zip(df["lat_adj"], df["lon_adj"])))


def convert_location_ids_to_coordinates(
    df: pd.DataFrame, location_id_coordinate_dict: dict, id_column_name: str
) -> np.ndarray:
    """
    Get numpy array of pairs of coordinates - one row for each ID in the input DataFrame

    Parameters:
        df (pd.DataFrame): Input dataframe with `lat_adj` and `lon_adj` columns, and a
        column with the same name as `id_column_name`
        location_id_coordinate_dict (dict): Dictionary of location IDs to coordinates
        id_column_name (str): Name of the column in `df` containing location IDs

    Returns:
        np.ndarray: Array of coordinates
    """
    return np.array(
        [location_id_coordinate_dict[id_val] for id_val in df[id_column_name].tolist()]
    )


def calculate_distances_between_lsoas_and_healthcare_locations(
    df_l: pd.DataFrame,
    coords_l: np.ndarray,
    df_r: pd.DataFrame,
    coords_r: np.ndarray,
) -> pd.DataFrame:
    """
    Calculate Euclidean distances between LSOAs and healthcare locations (e.g. dentists,
    GP practices)

    Parameters:
        df_l (pd.DataFrame): DataFrame of locations (often LSOAs) with a `unique_code_l`
        column.
        coords_l (np.ndarray): Array of coordinates for locations in `df_l` (in km)
        df_r (pd.DataFrame): DataFrame of locations (usually  healthcare locations) with
        a `unique_code_r` column.
        coords_r (np.ndarray): Array of coordinates for locations in `df_r` (in km)
        locations (in kilometres)

    Returns:
        pd.DataFrame: DataFrame of distances between `df_l` and `df_r` locations
    """
    distances: np.ndarray = sp.spatial.distance.cdist(
        coords_l, coords_r, "euclidean"
    )

    df = pd.DataFrame(distances)
    df.index = df_l["unique_code_l"].tolist()
    df.columns = df_r["unique_code_r"].tolist()
    return df


def get_nearest_locations_df(
    df: pd.DataFrame, n: int = 50, max_dist: float | None = None
) -> pd.DataFrame:
    """
    Function to get n nearest location ids from Euclidean distance matrix below a max
    distance.

    Parameters:
        df (pd.DataFrame): Euclidean distance matrix
        n (int): Number of nearest locations to return
        max_dist (float): Maximum distance to consider (in kilometres)

    Returns:
        pd.DataFrame: DataFrame of nearest healthcare locations to LSOAs
    """
    nearest_locations: dict = {}

    for id_val in df.index.tolist():
        vals: pd.Series = df.loc[id_val]

        # If a max_dist has been set then filter out above
        if max_dist:
            vals = vals[vals < max_dist]
            nearest_vals: pd.Series = vals.sort_values().index.tolist()[:n]

            if len(nearest_vals) < n:
                nearest_vals += [""] * (n - len(nearest_vals))
        else:
            nearest_vals: pd.Series = vals.sort_values().index.tolist()[:n]

        nearest_locations[id_val] = nearest_vals

    nearest_locations_df: pd.DataFrame = (
        pd.DataFrame(nearest_locations)
        .T.reset_index()
        .rename(columns={"index": "unique_code_l"})
    )
    return nearest_locations_df


def check_number_of_ids_with_fewer_than_max_number_of_locations(
    df: pd.DataFrame,
) -> list[str]:
    """
    Check if any locations have fewer than the max number of nearest locations within a
    max distance. There should be none.

    If there are any with fewer than the maximum number of locations, then the function
    will print out the number of LSOAs.

    Parameters:
        df (pd.DataFrame): DataFrame of `n` nearest locations

    Returns:
        list[str]: List of locations from left-hand dataset with fewer than the maximum
        number of nearest locations from right-hand dataset within a maximum distance
    """
    # The first column is the LSOA ID, so all OTHER columns are our healthcare locations
    index_with_empty_string: pd.Series = df.loc[:, 1 : len(df.columns) - 2].apply(
        lambda row: "" in row.values, axis=1
    )
    indices: pd.Index = df[index_with_empty_string].index
    if len(indices) != 0:
        print(
            f"{len(indices)} locations have fewer than the max no. of nearest locations within max distance"
        )
    return list(indices)


def lat_long_from_postcode(
    df: pd.DataFrame,
    postcode_lookup: pd.DataFrame,
)   -> pd.DataFrame:
    """
    Function to get latitude and longitude from postcodes.

    Parameters:
        df (pd.DataFrame): DataFrame of postcodes with `postcode` column.
        postcode_lookup (pd.DataFrame): DataFrame of postcodes with `postcode`, `latitude`,
        and `longitude` columns.
    Returns:
        pd.DataFrame: DataFrame of postcodes with `postcode`, `lat`, and `lon` columns.
    """
    
    # Drop country column
    postcode_lookup = postcode_lookup.drop(columns=["country"])

    # Remove spaces from lookup and df
    postcode_lookup["postcode"] = postcode_lookup["postcode"].str.replace(" ", "")
    df["postcode"] = df["postcode"].str.replace(" ", "")

    #Rename latitude and longitude columns to lat and lon
    postcode_lookup = postcode_lookup.rename(columns={"latitude": "lat", "longitude": "lon"})
    # Remove any rows with no postcode or ID
    df = df.dropna(subset=["postcode"])
    df = df.dropna(subset=["unique_code"])

    #Merge 
    df = df.merge(postcode_lookup, on="postcode", how="left")

    return df

def preprocess(
    df_l: pd.DataFrame,
    df_r: pd.DataFrame,
    n: int = 50,
    max_dist: float | None = None,
) -> pd.DataFrame:
    """
    Get a DataFrame of `n` nearest healthcare locations (within a maximum distance) for
    each LSOA.

    Parameters:
        df_l (pd.DataFrame): DataFrame of locations, with `unique_code`, `lat`, and `lon`
        columns. Often LSOA data. We will find distances from each of these locations to
        the `n` nearest locations in `df_r`
        df_r (pd.DataFrame): DataFrame of locations, with `unique_code`, `lat`, and `lon`
        columns. Often healthcare location data.
        n (int): Number of nearest locations to return
        max_dist (float): Maximum distance away from LSOAs to consider (in kilometres)

    Returns:
        pd.DataFrame: DataFrame of `n` nearest locations in df_r to each location in
        df_l, with latitudes and longitudes
    """


    df_l_rename = df_l.copy().rename(columns={"unique_code": "unique_code_l"})
    df_r_rename = df_r.copy().rename(columns={"unique_code": "unique_code_r"})


    df_l_km, df_r_km = (
        convert_lat_lon_to_km(df)
        for df in (df_l_rename, df_r_rename)
    )

    dict_l: dict = create_dict_of_location_ids_to_coordinates(
        df_l_rename, "unique_code_l"
    )
    dict_r: dict = create_dict_of_location_ids_to_coordinates(
        df_r_rename, "unique_code_r"
    )

    coords_l: np.ndarray = convert_location_ids_to_coordinates(
        df_l_km, dict_l, "unique_code_l"
    )
    coords_r: np.ndarray = convert_location_ids_to_coordinates(
        df_r_km, dict_r, "unique_code_r"
    )

    distances: pd.DataFrame = (
        calculate_distances_between_lsoas_and_healthcare_locations(
            df_l_km,
            coords_l,
            df_r_km,
            coords_r,
        )
    )

    nearest_locations_df: pd.DataFrame = get_nearest_locations_df(
        distances, n, max_dist
    )
    print(nearest_locations_df.shape)
    print(df_l_rename.shape)
    print(df_r_rename.shape)

    check_number_of_ids_with_fewer_than_max_number_of_locations(nearest_locations_df)
     
    # Find number of duplicates in df_r_rename in the unique_code_r column
    duplicate_count = df_r_rename["unique_code_r"].duplicated().sum()
    print(f"Number of duplicate unique_code_r entries: {duplicate_count}")
    # If there are more than 10 duplicate codes, stop the process
    if duplicate_count > 10:
        raise ValueError("Too many duplicate unique_code_r entries, stopping process")

    



    return_df = (
        nearest_locations_df
        .melt(
            id_vars=["unique_code_l"],
            value_vars=[col for col in nearest_locations_df.columns if col != "unique_code_l"]
        )
        .sort_values(["unique_code_l", "variable"])
        .reset_index(drop=True)
        .drop(columns="variable")
        .rename(columns={"value": "unique_code_r"})
        .merge(df_l_rename[["unique_code_l", "lat", "lon"]], on="unique_code_l", how="left")
        .rename(columns={"unique_code_l": "uniqueCodeL", "lat": "latL", "lon": "lonL"})
        .merge(df_r_rename[["unique_code_r", "lat", "lon"]], on="unique_code_r", how="left")
        .rename(columns={"unique_code_r": "uniqueCodeR", "lat": "latR", "lon": "lonR"})
    )[["uniqueCodeL", "latL", "lonL", "uniqueCodeR", "latR", "lonR"]]

    return return_df
