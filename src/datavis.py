"""
Functions for generating tables in Python to analyse the geographical distribution of healthcare locations.

"""

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from bng_latlon import OSGB36toWGS84, WGS84toOSGB36
from folium.plugins import HeatMap
from matplotlib.pyplot import figure
from shapely.geometry import Point

from src.read_write_data import load_config
from src.stats import aggregate_summary_upto_larger_geography


def OS_coordinate_to_lon_lat(
    df, x_column, y_column, lon_column_name, lat_column_name, lsoa_column
):
    """
    Convert the LSOA Population Weighted Centroid coordinates from OS standard to Lat and Lon.
    Renames the LSOA column to 'lsoaId', in-line with other tables in the database.

    Parameters:
        df (pd.DataFrame): dataframe containing the LSOA Population Weighted Centroid coordinates in OS standard.
        x_column (str): name of the column containing the x coordinate in OS Standard.
        y_column (str): name of the column containing the y coordinate in OS Standard.
        lon_column_name (str): name of the column to store the longitude.
        lat_column_name (str): name of the column to store the latitude.
        lsoa_column (str): name of the column containing the LSOA.

    Returns:
        df (pd.DataFrame): dataframe with the LSOA Population Weighted Centroid coordinates in Lat and Lon.

    """
    df[[lon_column_name, lat_column_name]] = df.apply(
        lambda row: OSGB36toWGS84(row[x_column], row[y_column]),
        axis=1,
        result_type="expand",
    )
    df = df.loc[:, [lsoa_column, lon_column_name, lat_column_name]]
    df.rename(columns={lsoa_column: "lsoaId"}, inplace=True)

    return df


def lon_lat_to_easting_northing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts latitude and longitude to the OS system, eastings and northings.

    Arguments:
        df (pd.DataFrame): Pandas DataFrame with a "lat" and "lon" column.
    
    Returns:
        pd.DataFrame: Input DataFrame with an "easting" and "northing" column.
    """
    df[["easting", "northing"]] = df.apply(
        lambda row: WGS84toOSGB36(row["lat"], row["lon"]), axis=1
    ).tolist()
    return df


def categorise_data(df, column, step):
    """
    Function used to categorise the data in the column specified by the user, into groups of the size specified by the user.
    Allows you to group the data by the time it takes to reach each healthcare location in each LSOA.

    Parameters:
        df (pd.DataFrame): dataframe containing the data to be categorised.
        column (str): name of the column to be categorised.
        step (int): size of the groups.

    Returns:
        categorised_data (pd.DataFrame): dataframe containing the data in categories.
    """
    df = df.dropna(subset=[column]).copy()
    maximum = int((df[column].max()) // 5) * 5
    bins = list(range(0, maximum, step))
    labels = [f"{bins[i]}-{bins[i+1]}" for i in range(len(bins) - 1)]

    df.loc[:, column] = pd.cut(df[column], bins=bins, labels=labels, right=False)
    categorised_data = df.groupby(column).size().reset_index(name="count")

    return categorised_data


def filtering_data_by_threshold(df, column_filter, threshold, column_group):
    """
    Function used to filter the data in the column specified by the user, by removing all rows where the value in the column is greater than the threshold specified by the user.

    Parameters:
        df (pd.DataFrame): dataframe containing the data to be filtered.
        column_filter (str): name of the column to be filtered.
        threshold (int): threshold value to be used for filtering.
        column_group (str): name of the column to group the data by.

    Returns:
        filtered_grouped_data (pd.DataFrame): dataframe containing the filtered data, grouped by the column specified by the user.

    """
    filtered_data = (df[df[column_filter] <= threshold]).reset_index(drop=True)
    filtered_grouped_data = (
        filtered_data.groupby(column_group).size().reset_index(name="count")
    )
    return filtered_grouped_data


def find_mean_travel_time_per_lsoa(df, lsoa_column, time_column):
    """
    Function used to find the mean travel time to a healthcare location in each LSOA.

    Parameters:
        df (pd.DataFrame): dataframe containing the travel times.
        lsoa_column (str): name of the column containing the LSOA.
        time_column (str): name of the column containing the travel time.

    Returns:
        mean_travel_time_per_lsoa (pd.DataFrame): dataframe containing the minimum travel time to a healthcare location for each LSOA.

    """

    mean_travel_time_per_lsoa = (
        df.groupby(lsoa_column)[time_column].mean().reset_index(name=time_column)
    )

    return mean_travel_time_per_lsoa


def plot_results(data, x_axis, y_axis, x_label, y_label):
    """
    Function used to plot a bar chart of the data in the dataframe specified by the user.

    Parameters:
        data (pd.DataFrame): dataframe containing the data to be plotted.
        x_axis (str): name of the column to be used for the x-axis.
        y_axis (str): name of the column to be used for the y-axis.
        x_label (str): label for the x-axis.
        y_label (str): label for the y-axis.

    Returns:
        bar chart
    """
    x = data[x_axis]
    y = data[y_axis]

    plt.figure(figsize=(20, 10))
    plt.xticks(rotation=0)
    plt.ylabel(y_label)
    plt.xlabel(x_label)
    plt.bar(x, y)
    plt.show()


def plot_results_percentage(data, x_axis, y_axis, x_label, y_label):
    """
    Function used to plot a bar chart of the data in the dataframe specified by the user, with the y-axis showing the percentage of the total.

    Parameters:
        data (pd.DataFrame): dataframe containing the data to be plotted.
        x_axis (str): name of the column to be used for the x-axis.
        y_axis (str): name of the column to be used for the y-axis.
        x_label (str): label for the x-axis.
        y_label (str): label for the y-axis.

    Returns:
        bar chart
    """
    x = data[x_axis]
    y = data[y_axis]

    total = sum(y)
    y_percentage = [i / total * 100 for i in y]

    plt.figure(figsize=(20, 10))
    plt.xticks(rotation=0)
    plt.ylabel(y_label)
    plt.xlabel(x_label)
    plt.bar(x, y_percentage)
    plt.show()


def plot_heatmap(df, lon_column, lat_column, value_column):
    """
    Function used to plot a heatmap of the data in the dataframe specified by the user.

    Note that with a contour map, a higher number is shown as red - i.e. an LSOA which has lots of healthcare locations within the threshold set is shown as red.

    Parameters:
        df (pd.DataFrame): dataframe containing the data to be plotted.
        lat_column (str): name of the column containing the latitude of the healthcare locations.
        lon_column (str): name of the column containing the longitude of the healthcare locations.
        count_column (str): name of the column containing the count that will be plotted.

    Returns:
        folium.Map: folium map object containing the heatmap.

    """
    map_center = [df[lon_column].mean(), df[lat_column].mean()]

    heat_map = folium.Map(location=map_center, zoom_start=7)

    data = [
        [row[lon_column], row[lat_column], row[value_column]]
        for _, row in df.iterrows()
    ]

    HeatMap(data).add_to(heat_map)

    return heat_map


def plot_circle_markers_map(df, lon_column, lat_column, value_column, circle_radius):
    """
    Function used to plot a map of the data in the dataframe specified by the user, using coloured circles to represent the number of healthcare locations within reach of a certain threshold.

    Parameters:
        df (pd.DataFrame): dataframe containing the number of healthcare locations located within a certain threshold from the LSOA PWC, for each LSOA.
        lat_column (str): name of the column containing the latitude of the healthcare locations.
        lon_column (str): name of the column containing the longitude of the healthcare locations.
        value_column (str): name of the column containing the count that will be plotted.
        circle_radius (int): radius of the circles that will be plotted.

    """

    map_center = [df[lon_column].mean(), df[lat_column].mean()]

    circles_map = folium.Map(location=map_center, zoom_start=6)

    def get_colour(count):
        if count >= 20:
            return "green"
        elif count >= 10:
            return "orange"
        else:
            return "red"

    for _, row in df.iterrows():
        folium.CircleMarker(
            location=[row[lon_column], row[lat_column]],
            radius=circle_radius,  # Radius of the circle marker
            color=get_colour(row[value_column]),
            fill=True,
            fill_color=get_colour(row[value_column]),
            fill_opacity=0.7,
        ).add_to(circles_map)

    return circles_map


def load_in_lsoa_population_data(file_path):
    """
    Function to load in the LSOA population data from the specified file path.
    Columns are renamed to be in-line with other dataframes used.
    The LSOA_population column is also adjusted to be an integer.

    Parameters:
        file_path (str): file path to the LSOA population data.

    Returns:
        lsoa_population_data (pd.DataFrame): dataframe containing the LSOA population data.

    """

    lsoa_population_data = pd.read_csv(file_path).rename(
        columns={"Total": "LSOA_population", "LSOA 2021 Code": "lsoaId"}
    )[["lsoaId", "LSOA_population"]]

    lsoa_population_data["LSOA_population"] = (
        lsoa_population_data["LSOA_population"].str.replace(",", "").astype(int)
    )

    return lsoa_population_data


def calculate_weighted_averages_for_constituencies(df1, df2, df3):
    """
    Function to calculate the weighted averages for each constituency.

    Parameters:
        df1 = dataframe containing the constituency shape data.
        df2 = dataframe containing the LSOA population data.
        df3 = dataframe containing the LSOA count and coordinates data.

    Returns:
        weighted_avg (pd.DataFrame): dataframe containing the weighted averages for each constituency.

    """

    lsoa_to_constituency_df = pd.merge(df1, df2, how="left", on="lsoaId")

    lsoa_counts_by_constituency = pd.merge(
        df3, lsoa_to_constituency_df, how="left", on="lsoaId"
    )

    lsoa_counts_by_constituency = lsoa_counts_by_constituency[
        ["lsoaId", "count", "LSOA21NM", "PCON25CD", "PCON25NM", "LSOA_population"]
    ].rename(columns={"PCON25CD": "ConstituencyId"})

    lsoa_counts_by_constituency["proportion_reachable_within_x_mins"] = (
        lsoa_counts_by_constituency["count"] / 50
    )
    lsoa_counts_by_constituency["n_people_in_LSOA_within_x_mins"] = (
        lsoa_counts_by_constituency["LSOA_population"]
        * lsoa_counts_by_constituency["proportion_reachable_within_x_mins"]
    )

    weighted_avg = lsoa_counts_by_constituency.groupby("ConstituencyId").agg(
        weighted_sum=("n_people_in_LSOA_within_x_mins", "sum"),
        total_population=("LSOA_population", "sum"),
    )
    weighted_avg["weighted_average"] = (
        weighted_avg["weighted_sum"] / weighted_avg["total_population"]
    )

    constituency_weighted_average = pd.merge(
        lsoa_counts_by_constituency, weighted_avg, how="left", on="ConstituencyId"
    )

    constituency_weighted_average = constituency_weighted_average[
        ["ConstituencyId", "weighted_average"]
    ]

    return constituency_weighted_average


def plot_constituencies_and_weighted_averages(df1, df2, column_name, legend_label):

    f, ax = plt.subplots(1, figsize=(10, 20))
    df1.plot(ax=ax, color="lightgrey")
    df2.plot(
        column=column_name,
        ax=ax,
        legend=True,
        legend_kwds={"label": legend_label, "orientation": "horizontal"},
    )
    ax.set_axis_off()

    return f, ax


def plot_map(
    summary_stats: pd.DataFrame,
    lsoa_lookup: pd.DataFrame,
    shapefile: gpd.GeoDataFrame,
    value_column: str,
    geography_id_column: str = "LSOA21CD",
    higher_is_worse: bool = True,
    **kwargs,
):
    """
    Function to plot a choropleth map of summary statistics. This function
    can aggregate up a dataframe of LSOAs to a larger geography.

    Parameters:
        summary_stats (pd.DataFrame): DataFrame containing one row per
        LSOA, with a field `value_column` containing some statistic for
        that LSOA.
        lsoa_lookup (pd.DataFrame): DataFrame looking up LSOA21CD to some
        other geography, each ICB23CD or PCON24CD.
        shapefile (gpd.GeoDataFrame): GeoDataFrame containing the geometry of
        the geography to be plotted.
        value_column (str): Name of the statistic column.
        geography_id_column: Name of the geography ID column, LSOA21CD,
        ICB23CD, or PCON24CD. Defaults to LSOA21CD.
        higher_is_worse (bool): Whether higher values of the statistic are
        "worse". Defaults to True.
    """
    if geography_id_column == "LSOA21CD":
        stats_aggregated = gpd.GeoDataFrame(
            summary_stats.merge(
                shapefile[[geography_id_column, "geometry"]],
                how="left",
                left_on="lsoa_id",
                right_on=geography_id_column,
            ).rename(columns={value_column: f"average_{value_column}"})
        )
    else:
        stats_aggregated = aggregate_summary_upto_larger_geography(
            summary_stats,
            lsoa_lookup,
            shapefile,
            value_column,
            geography_id_column,
        )
    fig, ax = plt.subplots()
    colour_map = "bwr" if higher_is_worse else "RdYlGn"
    stats_aggregated.plot(
        column=f"average_{value_column}",
        cmap=colour_map,
        ax=ax,
        legend=True,
        **kwargs,
        # norm=colors.TwoSlopeNorm(vcenter=10, vmin=0, vmax=30),
    )
    fig.set_facecolor("lightblue")
    ax.set_axis_off()
    plt.show()


def find_which_polygon_a_point_is_in(
    points_df: pd.DataFrame,
    shapefile: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Pairs a pandas DataFrame with a "lat" and "lon" column with a geopandas DataFrame
    with a "geometry" column. Essentially does a left join on the condition that the
    latitude and longitude of each location falls in a polygon.

    Arguments:
        points_df (pd.DataFrame): a pandas DataFrame with "lat" and "lon" columns
        shapefile (gpd.GeoDataFrame): a geopandas DataFrame with a "geometry" column

    Returns:
        gpd.GeoDataFrame: a geopandas DataFrame with a "geometry" column and the same
        number of rows as the `points_df` DataFrame. Data from `shapefile` are based
        on which polygon the location is in.
    """
    points_df = lon_lat_to_easting_northing(points_df)

    points_df["coords"] = points_df.apply(
        lambda row: Point(row["easting"], row["northing"]),
        axis=1,
    )

    cross_joined = gpd.GeoDataFrame(
        points_df.assign(cross_join_key=0)
        .merge(
            shapefile.assign(cross_join_key=0),
            on="cross_join_key",
        )
        .drop(columns="cross_join_key")
    )
    cross_joined["within"] = cross_joined.apply(
        lambda row: row["coords"].within(row["geometry"]),
        axis=1,
    )

    return_df: gpd.GeoDataFrame = (
        cross_joined.query("within")
        .drop(columns=["easting", "northing", "coords", "within"])
        .reset_index(drop=True)
    )

    return return_df
