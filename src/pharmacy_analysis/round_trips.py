from itertools import islice

import numpy as np
import pandas as pd

from src.stats import find_min_travel_time_per_lsoa


def get_top_n_round_trips(
    lsoas_to_gps: pd.DataFrame,
    lsoas_to_pharmacies: pd.DataFrame,
    gps_to_pharmacies: pd.DataFrame,
    gps: pd.DataFrame,
    n: int = 100,
    chunk_size: int = 2000,
) -> pd.DataFrame:
    """
    Joins together the LSOA to GP, GP to pharmacy, and LSOA to pharmacy routings. Adds
    times and distances together to approximate how long it takes to travel from each
    LSOA's PWC to a pharmacy via a GP, and then back to the PWC.

    In the case of dispensing GPs, total time is equal to double the time required to
    travel from the LSOA to the GP (it is assumed they will not then need to travel to
    a pharmacy).

    Args:
        lsoas_to_gps (pd.DataFrame): LSOA to GP routing dataframe, with `uniqueCodeL`,
        `uniqueCodeR`, `time`, `distance`, `transportProfile`, `sourceDatasetL` and
        `sourceDatasetR` columns.
        lsoas_to_pharmacies (pd.DataFrame): LSOA to pharmacy routing dataframe, with
        `uniqueCodeL`, `uniqueCodeR`, `time`, `distance`, `transportProfile`,
        `sourceDatasetL` and `sourceDatasetR` columns.
        gps_to_pharmacies (pd.DataFrame): GP to pharmacy routing dataframe, with
        `uniqueCodeL`, `uniqueCodeR`, `time`, `distance`, `transportProfile`,
        `sourceDatasetL` and `sourceDatasetR` columns.
        gps (pd.DataFrame): GP data
        n (int, optional): Top n round trips to include. Defaults to 100.
        chunk_size (int, optional): For efficiency reasons, how many LSOAs to chunk
        together when merging. Defaults to 2000.

    Returns:
        pd.DataFrame: Top n "round trips" for each LSOA.

    """

    # We cannot store enough data to merge all three dataframes together at once.
    # However it is very slow to merge the dataframes one LSOA at a time.
    # We combine the approaches by chunking up the LSOAs to merge them quickly 2000
    # or so at a time
    unique_codes: np.ndarray = lsoas_to_gps["uniqueCodeL"].unique()
    it = iter(unique_codes)
    lsoa_code_list: list[list[str]] = [
        list(islice(it, chunk_size))
        for _ in range((len(unique_codes) + chunk_size - 1) // chunk_size)
    ]

    all_merged = pd.DataFrame()
    for code_list in lsoa_code_list:
        merged = (
            lsoas_to_gps.loc[
                lsoas_to_gps["uniqueCodeL"].isin(code_list),
                ["uniqueCodeL", "uniqueCodeR", "time", "distance"],
            ]
            .add_suffix("_1")
            .merge(
                gps_to_pharmacies[
                    ["uniqueCodeL", "uniqueCodeR", "time", "distance"]
                ].add_suffix("_2"),
                how="left",
                left_on="uniqueCodeR_1",
                right_on="uniqueCodeL_2",
            )
            .drop(columns="uniqueCodeL_2")
            .merge(
                lsoas_to_pharmacies[
                    ["uniqueCodeL", "uniqueCodeR", "time", "distance"]
                ].add_suffix("_3"),
                how="inner",
                left_on=["uniqueCodeL_1", "uniqueCodeR_2"],
                right_on=["uniqueCodeL_3", "uniqueCodeR_3"],
            )
            .merge(
                gps[["unique_code", "is_dispensing_gp"]],
                how="left",
                left_on="uniqueCodeR_1",
                right_on="unique_code",
            )
            .rename(
                columns={
                    "uniqueCodeL_1": "lsoa_id",
                    "uniqueCodeR_1": "gp_id",
                    "uniqueCodeR_2": "pharmacy_id",
                }
            )
        )
        dispensing: pd.DataFrame = (
            merged.query("is_dispensing_gp")
            .assign(
                total_time=lambda df: 2 * df["time_1"],
                total_distance=lambda df: 2 * df["distance_1"],
            )
            .drop(columns=["pharmacy_id", "time_2", "time_3"])
            .drop_duplicates(["lsoa_id", "gp_id"])
        )
        non_dispensing: pd.DataFrame = merged.query("~is_dispensing_gp").assign(
            total_time=lambda df: df["time_1"] + df["time_2"] + df["time_3"],
            total_distance=lambda df: df["distance_1"]
            + df["distance_2"]
            + df["distance_3"],
        )
        concatenated: pd.DataFrame = (
            pd.concat([non_dispensing, dispensing])
            .drop(
                columns=[
                    "uniqueCodeL_3",
                    "uniqueCodeR_3",
                    "time_1",
                    "time_2",
                    "time_3",
                    "distance_1",
                    "distance_2",
                    "distance_3",
                    "unique_code",
                ]
            )
            .sort_values(["lsoa_id", "total_time"])
            .groupby("lsoa_id")
            .head(n)
        )

        all_merged = pd.concat([all_merged, concatenated], ignore_index=True)

    all_merged = all_merged.sort_values(["lsoa_id", "total_time"]).reset_index(
        drop=True
    )
    return all_merged


def join_round_trips_to_inputs(
    round_trips: pd.DataFrame,
    lsoa_pwcs: pd.DataFrame,
    gps: pd.DataFrame,
    pharmacies: pd.DataFrame,
) -> pd.DataFrame:
    """
    Take a round trips dataset and join each ID to the relevant input datasets.

    Args:
        round_trips (pd.DataFrame): DataFrame with an `lsoa_id`, `gp_id`,
        `pharmacy_id`, `is_dispensing_gp`, `total_time`, and `total_distance` column.
        lsoa_pwcs (pd.DataFrame): LSOA dataset
        gps (pd.DataFrame): GP dataset
        pharmacies (pd.DataFrame): Pharmacy dataset

    Returns:
        pd.DataFrame: DataFrame with `lsoa_id`, `gp_id`, `pharmacy_id`, `total_time`,
        `total_distance`, `is_dispensing_gp`, `lsoa_name`, `gp_name`, `pharmacy_name`,
        `population`, `Urban_rural_flag`, `lat_lon_lsoa`, `lat_lon_gp`, and
        `lat_lon_pharmacy` columns
    """
    joined: pd.DataFrame = (
        round_trips.merge(
            lsoa_pwcs.assign(
                lat_lon_lsoa=lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
            )[
                [
                    "unique_code",
                    "lat_lon_lsoa",
                    "LSOA21NM",
                    "Urban_rural_flag",
                    "population",
                ]
            ].rename(
                columns={"LSOA21NM": "lsoa_name"}
            ),
            how="left",
            left_on="lsoa_id",
            right_on="unique_code",
        )
        .drop(columns="unique_code")
        .merge(
            gps.assign(lat_lon_gp=lambda df: df[["lat", "lon"]].apply(tuple, axis=1))[
                ["unique_code", "lat_lon_gp", "name"]
            ].rename(columns={"name": "gp_name"}),
            how="left",
            left_on="gp_id",
            right_on="unique_code",
        )
        .drop(columns="unique_code")
        .merge(
            pharmacies.assign(
                lat_lon_pharmacy=lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
            )[["unique_code", "lat_lon_pharmacy", "trading_name"]].rename(
                columns={"trading_name": "pharmacy_name"}
            ),
            how="left",
            left_on="pharmacy_id",
            right_on="unique_code",
        )
        .drop(columns="unique_code")
    )[
        [
            "lsoa_id",
            "gp_id",
            "pharmacy_id",
            "total_time",
            "total_distance",
            "is_dispensing_gp",
            "lsoa_name",
            "gp_name",
            "pharmacy_name",
            "population",
            "Urban_rural_flag",
            "lat_lon_lsoa",
            "lat_lon_gp",
            "lat_lon_pharmacy",
        ]
    ]
    return joined


def summarise_round_trip_stats(
    df: pd.DataFrame,
    lsoa_data: pd.DataFrame,
    gp_data: pd.DataFrame,
    pharmacy_data: pd.DataFrame,
    thresholds: list[int],
    time_col: str = "total_time",
) -> pd.DataFrame:
    """
    Produce summary statistics for a "round trip" dataset.

    Parameters:
        df (pd.DataFrame): DataFrame with `lsoa_id`, `gp_id`, `pharmacy_id`,
        `total_time`, `total_distance`, `is_dispensing_gp`, `lsoa_name`.
        lsoa_data (pd.DataFrame): LSOA dataset
        gp_data (pd.DataFrame): GP dataset
        pharmacy_data (pd.DataFrame): Pharmacy dataset
        thresholds (list[int]): list of thresholds to use for the number of
        routes completable within a given time.
        time_col (str): Column name for the time column. Default is "total_time".

    Returns:
        pd.DataFrame: DataFrame with one row per LSOA.
    """

    threshold_stats = df[["lsoa_id"]].drop_duplicates().reset_index(drop=True)
    for t in thresholds:
        threshold_stats = threshold_stats.merge(
            df[df[time_col]<=t].groupby("lsoa_id").size().rename(f"number_of_locations_within_{t}_minutes"),
            how="left",
            on="lsoa_id"
        )
    threshold_stats = threshold_stats.fillna(0)

    min_time_stats = (
        df
        .sort_values(time_col)
        .groupby("lsoa_id")
        .head(1)
        .reset_index(drop=True)
        .rename(columns={time_col: "min_time"})
    )
    # find_min_travel_time_per_lsoa(
    #     df, "lsoa_id", time_col
    # )[["lsoa_id", "uniqueCodeR", time_col, "distance"]].rename(columns={time_col: "min_time", "uniqueCodeR": "location_id"})

    stats = (
        min_time_stats
        .merge(threshold_stats, how="left", on="lsoa_id")
        .merge(lsoa_data, how="left", left_on="lsoa_id", right_on="unique_code")
        .assign(
            lat_lon_lsoa = lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
        )
        .drop(columns=["unique_code", "lat", "lon", "RUC21CD", "RUC21NM"])
        .merge(
            gp_data[["unique_code", "name", "lat", "lon", "number_of_dispensing_gps"]],
            how="left",
            left_on="gp_id",
            right_on="unique_code",
        )
        .rename(columns={"name": "gp_name"})
        .assign(
            lat_lon_gp = lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
        )
        .drop(columns=["unique_code", "lat", "lon"])
        .merge(
            pharmacy_data,
            how="left",
            left_on="pharmacy_id",
            right_on="unique_code",
        )
        .assign(
            lat_lon_pharmacy = lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
        )
        .drop(columns=["unique_code", "lat", "lon", "postcode"])
        .rename(columns={"trading_name": "pharmacy_name", "organisation_name": "pharmacy_org_name"})  
    )
    return stats
