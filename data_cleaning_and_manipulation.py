# Databricks notebook source
# MAGIC %md
# MAGIC ## Data cleaning and manipulation

# COMMAND ----------

# MAGIC %md
# MAGIC This notebook:
# MAGIC - Reads in ONS LSOA population-weighted centroids (centrepoints) data for England and Wales, removes Welsh LSOAs
# MAGIC - Converts LSOA centrepoint locations from OSGB co-ordinates to Lon/Lats and saves the dataset
# MAGIC - Reads in ONS postcode centroids data
# MAGIC - Reads in various healthcare locations datasets (Start for Life centers, GPs, pharmacies)
# MAGIC  

# COMMAND ----------

import numpy as np
import pandas as pd

from src.data_cleaning import (
    create_lat_lon_columns,
    drop_locations_with_no_lat_lon,
    filter_out_wales,
    OSGB_to_LatLon
)
from src.preprocess import (
    preprocess,
    lat_long_from_postcode
)
from src.read_write_data import (
    download_csv_data_from_url,
    load_config,
    read_healthcare_locations_data,
    write_dataset,
)

pd.options.mode.chained_assignment = None  # mute SettingWithCopyWarnings

# COMMAND ----------

# MAGIC %md
# MAGIC #### Load config

# COMMAND ----------

config = load_config()

# COMMAND ----------

# MAGIC %md
# MAGIC #### LSOAs

# COMMAND ----------

# lsoa_pwcs: pd.DataFrame = (
#     create_lat_lon_columns(
#         filter_out_wales(
#             pd.read_csv(config["lsoa_pwc_data_file_path"])
#         )
#     )[
#         ["LSOA21CD", "lat", "lon"]
#     ].rename(columns={"LSOA21CD": "unique_code"})
#     # pd.read_csv(config["lsoa_pwc_clean_data_file_path"])
#     .merge(
#         pd.read_csv(config["lsoa_rural_urban_classification"]),
#         how="left",
#         left_on="unique_code",
#         right_on="LSOA21CD",
#         validate="one_to_one",
#     )
#     .merge(
#         pd.read_csv(config["lsoa_population_data"]),
#         how="left",
#         left_on="unique_code",
#         right_on="LSOA 2021 Code"
#     )
#     .rename(columns={"Total": "population"})
#     .assign(population=lambda df: df.population.str.replace(',', '').astype(int))
# )[
#     ["unique_code", "lat", "lon", "LSOA21NM", "RUC21CD", "RUC21NM", "Urban_rural_flag", "population"]
# ]
# write_dataset(lsoa_pwcs, config["lsoa_pwc_clean_data_file_path"], specify_date=False)
lsoa_pwcs = pd.read_csv(config["lsoa_pwc_clean_data_file_path"])
lsoa_pwcs

# COMMAND ----------

# MAGIC %md
# MAGIC #### Postcodes (if needed)

# COMMAND ----------

# postcodes_url = config["ons_postcodes_url"]
# postcodes_columns_string = "postcode string, status string, usertype string, easting int, northing int, positional_quality_indicator int, country string, latitude float, longitude float, postcode_no_space string, postcode_fixed_width_seven string, postcode_fixed_width_eight string, postcode_area string, postcode_district string, postcode_sector string, outcode string, incode string"
# postcodes_desired_columns = ["postcode", "latitude", "longitude", "country"]
# postcodes_type_changes = {}

# # load postcodes data
# postcodes: pd.DataFrame = download_csv_data_from_url(
#       postcodes_url,
#       postcodes_columns_string,
#       postcodes_desired_columns,
#       postcodes_type_changes
#   )

# write_dataset(postcodes, config["postcodes_file_path"], specify_date=False)

postcodes: pd.DataFrame = pd.read_csv(config["postcodes_file_path"])
postcodes

# COMMAND ----------

#Read in source data for SfL
sfl_data = pd.read_csv(config["sfl_raw_location_file"],
                       encoding="latin-1")


# Find postcode
if "lat" in sfl_data.columns:
    print("Latitudes and longitudes already known")
else: 
    print("Getting latitudes and longitudes from postcodes")
    sfl_data = lat_long_from_postcode(sfl_data,
                                    postcode_lookup = postcodes)
    print("sfl_data has the following number of rows")
    print(sfl_data.shape)

print("Writing out file to")
print(config["sfl_data_file_path"])
# Write out data 
write_dataset(sfl_data,
              config["sfl_data_file_path"],
              specify_date = False)                      

# COMMAND ----------

# MAGIC %md
# MAGIC #### GP Data
# MAGIC
# MAGIC Practice data and then branches data are loaded and concatenated.
# MAGIC
# MAGIC The practices dataset is filtered for locations with:
# MAGIC
# MAGIC * the "GP practice" prescribing setting code, (so that pharmacies, prisons, etc. are not included);
# MAGIC * no `close_date` value;
# MAGIC * the active `status_code` value;
# MAGIC * non-Welsh `national_grouping` (code is NOT 'W00').
# MAGIC
# MAGIC All branches will have a `parent_organisation_code`, and no non-branches will have this code. The branches dataset is filtered for locations with:
# MAGIC
# MAGIC * no `close_date` value;
# MAGIC * only locations *not* labelled as a "COVID VACCINATION SERVICE" or "COVID19 TRIALS";
# MAGIC * non-Welsh `national_grouping` (code is NOT 'W00').
# MAGIC
# MAGIC We now concatenate the two datasets.
# MAGIC
# MAGIC Some practices are dispensing practices - we find these by merging with the list of dispensing GPs to add a label and number of dispensing GPs.
# MAGIC
# MAGIC We merge to the postcodes dataset to get latitudes and longitudes for each practice and branch.

# COMMAND ----------

# gp_practice_url = config["gp_practice_data_url"]
# gp_practice_columns_string = "organisation_code string, name string, national_grouping string, high_level_health_geography string, address_line_1 string, address_line_2 string, address_line_3 string, address_line_4 string, address_line_5 string, postcode string, open_date string, close_date string, status_code string, organisation_subtype_code string, commissioner string, join_provider_purchaser_date date, left_provider_purchaser_date date, contact_telephone_number string, column_19 string, column_20 string, column_21 string, amended_record_indicator int, column_23 string, provider_purchaser string, column_25 string, prescribing_setting int, column_27 string"
# gp_practice_desired_columns = ['organisation_code', 'name', 'postcode']
# gp_practice_type_changes = {}

# gp_branches_url = config["gp_branches_data_url"]
# gp_branches_columns_string = "organisation_code string, name string, national_grouping string, high_level_health_geography string, address_line_1 string, address_line_2 string, address_line_3 string, address_line_4 string, address_line_5 string, postcode string, open_date string, close_date string, column_13 string, column_14 string, parent_organisation_code string, join_parent_date date, left_parent_date date, contact_telephone_number string, column_19 string, column_20 string, column_21 string, amended_record_indicator int, column_23 string, GOR_code string, column_25 string, column_26 string, column_27 string"
# gp_branches_desired_columns = ['organisation_code', 'name', 'postcode', 'parent_organisation_code']
# gp_branches_type_changes = {}

# gp_practices: pd.DataFrame = download_csv_data_from_url(
#     gp_practice_url, gp_practice_columns_string,
# )
# gp_practices["open_date"] = pd.to_datetime(gp_practices["open_date"], format="%Y%m%d")
# gp_practices["close_date"] = pd.to_datetime(gp_practices["close_date"], format="%Y%m%d")
# active_gps = (
#     gp_practices
#     .query("prescribing_setting == 4 and close_date.isnull() and status_code=='A' and national_grouping != 'W00'")
#     [gp_practice_desired_columns]
# )

# gp_branches: pd.DataFrame = download_csv_data_from_url(
#     gp_branches_url, gp_branches_columns_string,
# )
# gp_branches["open_date"] = pd.to_datetime(gp_branches["open_date"], format="%Y%m%d")
# gp_branches["close_date"] = pd.to_datetime(gp_branches["close_date"], format="%Y%m%d")

# gp_branches_filter = (
#     gp_branches
#     .query(
#         "close_date.isnull() and ~name.str.contains('COVID (LOCAL )?VACCINATION SERVICE') and ~name.str.contains('COVID19 TRIAL') and national_grouping != 'W00'"
#     )
#     [gp_branches_desired_columns]
# )

# dispensing_gps = pd.read_csv(config["dispensing_gps_list_file_path"])
# dispensing_gps

# gp_data_active_and_branch = (
#     pd.concat([gp_branches_filter, active_gps])
#     .rename(columns={"organisation_code": "unique_code"})
# )
# gp_data_with_lat_lon = drop_locations_with_no_lat_lon(
#     gp_data_active_and_branch
#     .merge(postcodes, on="postcode", how="left")
#     .rename(columns={"latitude": "lat", "longitude": "lon"})
# )

# gp_data_with_dispensing_flag: pd.DataFrame = (
#     gp_data_with_lat_lon
#     .merge(dispensing_gps, how="left", left_on="unique_code", right_on="PRACTICE_CODE")
#     .assign(
#         is_dispensing_gp = lambda df: ~df["PRACTICE_CODE"].isna(),
#         number_of_dispensing_gps = lambda df: df["DISPENSING _GPS"].apply(lambda x: 0 if np.isnan(x) else int(x))
#     )
# )[gp_data_with_lat_lon.columns.to_list() + ["is_dispensing_gp", "number_of_dispensing_gps"]]
# gp_data = gp_data_with_dispensing_flag.copy().drop(columns="country")

# write_dataset(gp_data, config["gp_data_file_path_new"], specify_date=False)

#gp_data = pd.read_csv(config["gps_clean"])
#gp_data

# COMMAND ----------

# MAGIC %md
# MAGIC #### Pharmacy data

# COMMAND ----------

# pharmacies = (
#     pd.read_csv(config["pharmacies_url"])[
#         [
#             "PHARMACY_ODS_CODE_(F-CODE)",
#             "POST_CODE",
#             "PHARMACY_TRADING_NAME",
#             "ORGANISATION_NAME",
#             "CONTRACT_TYPE"
#         ]
#     ]
#     .rename(
#         columns={
#             "PHARMACY_ODS_CODE_(F-CODE)": "unique_code",
#             "POST_CODE": "postcode",
#             "PHARMACY_TRADING_NAME": "trading_name",
#             "ORGANISATION_NAME": "organisation_name",
#             "CONTRACT_TYPE": "contract_type"}
#     )
# )
# # write_dataset(pd.read_csv(config["pharmacies_url"]), config["pharmacies_downloaded_data"], specify_date=True)
# # display(pharmacies)
# pharmacies_with_lat_lon = drop_locations_with_no_lat_lon(
#     pharmacies
#     .merge(postcodes, on="postcode", how="left")
#     .rename(columns={"latitude": "lat", "longitude": "lon"})
# )

# pharmacies_lps_community_only = pharmacies_with_lat_lon[
#     pharmacies_with_lat_lon["contract_type"].isin(["Community", "LPS"])
# ].reset_index(drop=True)

# pharmacies_clean = pharmacies_lps_community_only.copy().drop(columns="country")
# write_dataset(pharmacies_clean, config["pharmacies_clean_new"], specify_date=False)

#pharmacies_clean = pd.read_csv(config["pharmacies_clean"])
#pharmacies_clean
