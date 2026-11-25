import geopandas as gpd
import pandas as pd


def find_min_travel_time_per_lsoa(df, lsoa_column, time_column):
    """
    Function used to find the minimum travel time to a healthcare location in each LSOA.

    Parameters:
        df (pd.DataFrame): dataframe containing the travel times. 
        lsoa_column (str): name of the column containing the LSOA.
        time_column (str): name of the column containing the travel time.

    Returns:
        min_travel_time_per_lsoa (pd.DataFrame): dataframe containing the minimum travel time to a healthcare location for each LSOA.
    
    """
    min_travel_time_per_lsoa = (
        df
        .sort_values(time_column)
        .groupby(lsoa_column)
        .head(1)
        .reset_index(drop=True)
    )
    return min_travel_time_per_lsoa


def bin_values(df: pd.DataFrame, column: str, bins: list[int]) -> pd.DataFrame:
    """
    Produce a "[value]_binned" field for some field in a data frame, binning
    the column into str values given by the bins list.

    Parameters:
        df (pd.DataFrame): dataframe containing the column to bin.
        column (str): name of the column to bin.
        bins (list[int]): list of bin edges.

    Returns:
        pd.DataFrame: dataframe containing the binned column.
    """
    bins.sort()
    df_column_max_value: float | int = df[column].max()
    if df_column_max_value > bins[-1]:
        bins.append(df_column_max_value)

    labels_list = [f"[{bins[0]}, {bins[1]}]"]
    for idx, elem in enumerate(bins[1:-1], start=1):
        labels_list.append(f"({elem}, {bins[idx+1]}]")

    return_df: pd.DataFrame = (
        df
        .assign(
            values_binned = lambda df: pd.cut(
                df[column],
                bins=bins,
                labels=labels_list,
                include_lowest=True,
            )
        )
        .rename(columns={"values_binned": f"{column}_binned"})
    )
    return return_df


def summarise_stats(
    df: pd.DataFrame,
    lsoa_data: pd.DataFrame,
    healthcare_location_data: pd.DataFrame,
    thresholds: list[int],
    time_col: str = "time",
) -> pd.DataFrame:
    """
    Function used to summarise the statistics of the travel times to
    healthcare locations for each LSOA. It finds the minimum travel time
    to a healthcare location from a given LSOA, and the number of locations
    with a given threshold of time.

    Parameters:
        df (pd.DataFrame): dataframe containing the travel times. Has an
        `lsoa_id` field.
        lsoa_data (pd.DataFrame): dataframe describing each LSOA.
        healthcare_location_data (pd.DataFrame): dataframe describing each
        healthcare location.
        thresholds (list[int]): list of thresholds to use for the number of
        locations within a given time.
        time_col (str): name of the column containing the travel time. Defaults
        to "time".

    Returns:
        pd.DataFrame: dataframe containing the statistics, one row per LSOA.
    """
    df = df.rename(columns={"uniqueCodeL": "lsoa_id"}).query("~time.isnull()")

    threshold_stats = df[["lsoa_id"]].drop_duplicates().reset_index(drop=True)
    for t in thresholds:
        threshold_stats = threshold_stats.merge(
            df[df[time_col]<=t].groupby("lsoa_id").size().rename(f"number_of_locations_within_{t}_minutes"),
            how="left",
            on="lsoa_id"
        )
    threshold_stats = threshold_stats.fillna(0)

    min_time_stats = (
        find_min_travel_time_per_lsoa(
            df, "lsoa_id", time_col
        )[["lsoa_id", "uniqueCodeR", time_col, "distance"]]
        .rename(
            columns={
                time_col: "min_time",
                "uniqueCodeR": "min_time_location_id",
            }
        )
    )

    stats = (
        # The column ordering here means that LSOA info is given first,
        # then stats info, then the info for the closest location.
        lsoa_data
        .merge(
            min_time_stats[
                ["lsoa_id"] +
                [
                    col for col in min_time_stats.columns
                    if col not in ["lsoa_id", "min_time_location_id"]
                ] +
                ["min_time_location_id"]
            ],
            how="left",
            left_on="unique_code",
            right_on="lsoa_id"
        )
        .merge(threshold_stats, how="left", on="lsoa_id")
        .assign(
            lat_lon_lsoa = lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
        )
        .drop(columns=["lsoa_id", "lat", "lon", "RUC21CD", "RUC21NM"])
        .rename(columns={"unique_code": "lsoa_id"})
        .merge(
            healthcare_location_data,
            how="left",
            left_on="min_time_location_id",
            right_on="unique_code",
        )
    )

    if 'lat' in stats.columns and 'lon' in stats.columns:
        stats = (stats.assign(
            lat_lon_location = lambda df: df[["lat", "lon"]].apply(tuple, axis=1)
         )
        .drop(columns=["unique_code", "lat", "lon", "postcode"])
        )
    else:
        stats = (stats.assign(
            lat_lon_location = lambda df: df['postcode']
         )
        .drop(columns=["unique_code", "postcode"])
        )
            
    return stats


def aggregate_summary_upto_larger_geography(
    summary_stats: pd.DataFrame,
    lsoa_lookup: pd.DataFrame,
    shapefile: gpd.GeoDataFrame,
    value_column: str,
    geography_id_column: str,
) -> gpd.GeoDataFrame:
    """
    Function to aggregate the LSOA geography up to a larger geography, with
    one row per larger geography.

    Parameters:
        summary_stats (pd.DataFrame): DataFrame containing one row per
        LSOA, with a field `value_column` containing some statistic for
        that LSOA.
        lsoa_lookup (pd.DataFrame): DataFrame looking up LSOA21CD to some
        other geography, each ICB23CD or PCON24CD.
        shapefile (gpd.GeoDataFrame): GeoDataFrame containing the geometry of
        the geography to be plotted.
        value_column (str): Name of the statistic column. This statistic will
        be multiplied by the population of each LSOA, then the average for the
        whole larger geography will be found to produce the aggregated statistic.
        geography_id_column: Name of the geography ID column, ICB23CD, or PCON24CD.
    
    Returns:
        gpd.GeoDataFrame: GeoDataFrame containing one row per geography.
    """
    stats_aggregated = (
        summary_stats
        .merge(
            lsoa_lookup[["LSOA21CD", geography_id_column]],
            how="left",
            left_on="lsoa_id",
            right_on="LSOA21CD"
        )
        .query(f"~{value_column}.isnull()")
        .assign(
            # average value for a larger geography = sum(value * population) / sum(population)
            value = lambda df: df[value_column] * df["population"]
        )
        .groupby(geography_id_column)
        .agg(
            {
                "value": sum,
                "population": sum,
            }
        )
        .reset_index()
        .assign(value = lambda df: df["value"] / df["population"])
        .merge(
            shapefile[[geography_id_column, "geometry"]],
            how="left",
            on=geography_id_column,
        )
        .rename(columns={"value": f"average_{value_column}"})
    )
    return gpd.GeoDataFrame(stats_aggregated)


def aggregate_stats_by_geography(
    df: pd.DataFrame,
    geography: str,
    stats_cols: list[str],
) -> pd.DataFrame:
    """
    Aggregate some LSOA stats up to a larger geography

    Parameters:
        df (pd.DataFrame): dataframe containing  summary statistics,
        one row per LSOA, a column matching the geography parameter, and
        a population column.
        geography (str): `ICB23CD` or `PCON24CD`.
        stats_col (list[str]): list of columns to be aggregated

    Returns:
        pd.DataFrame: dataframe containing the geography column, a total
        population column, and each of the stats columns, with a suffix
        "_weighted_average".
    
    """
    filtered = (
        df[
            [
                geography,
                "population",
            ] + 
            stats_cols
        ]
    ).query(f"~{stats_cols[0]}.isnull()")
    for col in stats_cols:
        filtered[col] = filtered[col] * filtered["population"]

    grouped = filtered.groupby(geography).sum().reset_index()
    for col in stats_cols:
        grouped[col] = grouped[col] / grouped["population"]
    grouped = grouped.rename(
        columns={k: f"{k}_weighted_average" for k in stats_cols}
    )

    return grouped
