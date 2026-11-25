"""
Functions for downloading, reading in, and outputting data
"""

import io
import os
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yaml
from pyspark.sql.session import SparkSession

# Get Spark session so functions can be used
spark = SparkSession.builder.getOrCreate()

# Get today's date for suffixing to created files
TODAY_DATE: str = datetime.today().strftime("%Y-%m-%d")


def load_config(file_path: Path | str = "config.yml") -> dict:
    """
    Read in the configuration file.

    Parameters:
        file_path (Path or str): Path to the configuration file. The default is
        "config.yml".

    Returns:
        dict: Configuration dictionary
    """
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def insert_date_into_file_path(file_path: Path | str) -> Path:
    """
    Sometimes we will want to store a generic version of a file name, that might
    need to have today's date inserted. This function inserts the date to the end of the
    file base name.

    Parameters:
        file_path (Path or str): Path to the file to modify

    Returns:
        Path: File path with date inserted - assuming the date was not already contained
    """
    if not isinstance(file_path, Path):
        file_path: Path = Path(file_path)
    dirname, stem, extension = file_path.parent, file_path.stem, file_path.suffix
    if str(TODAY_DATE) not in stem:
        stem = f"{stem}_{TODAY_DATE}"
    file_path = dirname / f"{stem}{extension}"
    return file_path


def download_csv_data_from_url(
    url: str,
    columns_string: str,
    desired_columns: list[str] | None = None,
    type_changes: dict[str:str] | None = None,
) -> pd.DataFrame:
    """
    Download zip file containing postcodes data, and outputs every postcode with their
    corresponding latitudes and longitudes.

    Parameters:
        url (str): URL of the data to download
        columns_string (str): String of column names to read in, separated by commas
        and including data type e.g. "postcode string, latitude float, longitude float"
        desired_columns (list[str]): Optional list of column names to return in the
        final dataframe
        type_changes (dict[str:str]): Optional ictionary of column names and their
        desired types e.g. {"postcode": "string"}

    Returns:
        pd.DataFrame: Pandas DataFrame containing data with the desired columns
    """
    zip_bin_data: bytes = requests.get(url).content
    byte_file = io.BytesIO(zip_bin_data)

    with zipfile.ZipFile(byte_file, "r") as zip_ref:
        entry_name: zipfile.ZipInfo = zip_ref.filelist[0]
        csv_bin_data: bytes = zip_ref.read(entry_name)

    csv_data: str = csv_bin_data.decode("utf-8")
    lines: list[str] = csv_data.splitlines()

    dt: pyspark.rdd.RDD = spark.sparkContext.parallelize(lines)
    df: pyspark.sql.DataFrame = spark.read.csv(
        dt,
        columns_string,
    )

    if desired_columns is None:
        df_pandas_select = df.toPandas()
    else:
        df_pandas_select = df.select(desired_columns).toPandas()

    if type_changes is None:
        df_pandas = df_pandas_select
    else:
        df_pandas = df_pandas_select.astype(type_changes)

    return df_pandas


def read_healthcare_locations_data(file_path: Path | str) -> pd.DataFrame:
    """
    Read in data about healthcare locations (`Location ID`, `Location Name`,
    `Location UPRN ID`, `Location Longitude` and `Location Latitude` fields
    only).

    Parameters:
        file_path (Path or str): Path to the file to read in

    Returns:
        pd.DataFrame: Healthcare locations DataFrame with `Location ID`,
        `Location Name`, `Location Longitude` and `Location Latitude` fields
    """
    df: pd.DataFrame = pd.read_excel(
        file_path,
        sheet_name="Sheet1",
        converters={
            "Location ID": str,
            "Location Name": str,
            "Location UPRN ID": str,
            "Location Latitude": float,
            "Location Longitude": float,
        },
    )[
        [
            "Location ID",
            "Location Name",
            "Location UPRN ID",
            "Location Latitude",
            "Location Longitude",
        ]
    ]

    return df


def load_partitioned_csv(folder_path, pattern="part-*") -> pd.DataFrame:
    """
    Loads and concatenates CSV files matching a pattern from a folder into a single
    DataFrame.

    Parameters:
        folder_path (str or Path): Path to the folder containing CSV partitioned files.
        pattern (str): Glob pattern to match file names (default is 'part-*').

    Returns:
        pd.DataFrame: Concatenated DataFrame from all matching CSV files.
    """
    folder = Path(folder_path)
    if os.path.exists(folder) and not os.path.isdir(folder):
        return pd.read_csv(folder)
    files: list[Path] = sorted(folder.glob(pattern))

    if not files:
        raise FileNotFoundError(
            f"No files matching pattern '{pattern}' found in {folder_path}"
        )

    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def read_in_route(
    database_path: str | Path,
    where_from: str,
    where_to: str,
    transport_profile: str,
    n: int = 50,
    date: str | None = None,
    testing_mode: bool = False,
) -> pd.DataFrame:
    """
    Read in a route DataFrame from a folder. Folders will begin with one of "test" or
    "results", list what datasets they are mapping from and to, how many locations
    each location in the origin dataset is mapping to, via what mode of transport, and
    possibly give a date in the format "%Y-%m-%d-%H%M%S". The folder contains a file or
    folder called "point_to_point.csv".

    Parameters:
        database_path (str or Path): Path to the folder containing the route DataFrame
        where_from (str): Name of the origin dataset
        where_to (str): Name of the destination dataset
        transport_profile (str): "car", "foot", or "bike".
        n (int): Number of locations in the destination dataset mapped to by each
        location in the origin dataset. The default is 50.
        date (str or None): Date of creation of the route DataFrame, in the format
        "%Y-%m-%d-%H%M%S". The default is `None`.
        testing_mode (bool): Is the file a test run? Default is False.

    Returns:
        df (pd.DataFrame): Dataset stored at the specified location.
    """
    database_path = Path(database_path)
    run_type: str = "test" if testing_mode else "results"
    folder_stem: str = f"{run_type}_{where_from}_{where_to}_{transport_profile}_{n}_locations"
    folder_name: str = folder_stem if date is None else f"{folder_stem}_{date}"
    df = load_partitioned_csv(Path(database_path) / folder_name / "point_to_point.csv")
    return df


def write_dataset(
    df: pd.DataFrame, write_path: Path | str, specify_date: bool = True
) -> None:
    """
    Write a DataFrame to a file. If the `specify_date` parameter is set to `True`, then
    today's date will be added to the file name.

    Parameters:
        df (pd.DataFrame): DataFrame to save
        write_path (Path or str): Path to write the file to
        specify_date (bool): Whether or not to add today's date to the file name. The
        default is `True`.
    """
    if specify_date:
        write_path: Path = insert_date_into_file_path(write_path)
    elif isinstance(write_path, str):
        write_path = Path(write_path)

    extension: str = write_path.suffix
    if extension == "":
        extension = ".csv"
        write_path.with_suffix(extension)

    if extension == ".csv":
        df.to_csv(write_path, index=False)
    elif extension in (".xls", ".xlsx", ".xlsm"):
        df.to_excel(write_path, index=False)
    elif extension == ".parquet":
        df.to_parquet(write_path, index=False)
