# GeoDe geospatial routing tool

## Analysis of access to healthcare setting using OS road data

This repository contains the underlying code for the Department of Health and Social Care's GeoDe tool, built originally to analyse access to healthcare settings in England and identify healthcare "deserts", using travel time and road network distance. This analysis uses Ordnance Survey (OS) Multi-Modal Routing Network data.

## How to get started

To run the code, you will need access to the Graph Hopper Open Source Routing Engine and Python. The codebase is built to run in Databricks.

You will need a `config.yml` file in the root directory of the project. This will look similar to the below:

```yaml
pbfDbfsStorage: "..."
graphDbfsStorage: "..."
graphLocalStorage: "..."
dataset_l_file_path: "..."
dataset_r_file_path: "..."
source_dataset_l_name: "..." # this is a nickname for the dataset - e.g. "lsoa_pwcs"
source_dataset_r_name: "..." # this is a nickname for the dataset - e.g. "pharmacies"
number_of_locations_to_use: 50 # This code finds the distance from each LSOA to the nearest n locations
transport_profile: "..." # car_fastest, foot_fastest, foot_shortest, or bike_fastest
database_path: "..." 
save_directory: "..."
run_in_testing_mode: true
specify_date: false # If this is true then this will add the date to the output filename
# Optionally add the following to specify the name of the output folder
# output_folder_name: "..."
```

### Running the system start to finish

* (Once per project) Once the OS Multi Modal Routing tool has been saved as a `.pbf` file at the file path with the `pbfDbfsStorage` key in the config, the `loadSaveCache` notebook can be run (this usually only needs doing once at the start of the project) and subsequently will not need repeating. This caches a version of the routing tool with desired transport profiles (at present, "car_fastest", "foot_fastest", "foot_shortest", and "bike_fastest"), and saves it to the file path with the `graphDbfsStorage` key in the config.
* The system requires two input datasets (known from now on as a left-hand and right-hand dataset). Usually these will be LSOA population weighted centroids (PWCs) on the left, and some sort of healthcare location (e.g. dentists, GPs, care homes, pharmacies) on the right. The datasets should *both* have the following schema (additional fields are allowed but not required): 

  unique_code|lat|lon
  ---|---|---
  id1|50.01449|-4.32154

  LSOA population-weighted centroid, GP practice, pharmacy, and ONS postcode datasets are already saved and accessible on the DAC in this format. The `data_cleaning_and_manipulation` notebook details the cleaning steps taken to prepare these for use. This will allow you to find the latitude and longitude from the postcode if needed.

  Note: you can also give the notebook a dataset with columns `uniqueCodeL`, `latL`, `lonL`, `uniqueCodeR`, `latR`, `lonR`, and pass this to the Scala part of the notebook. This will find the routes from each `uniqueCodeL` to each `uniqueCodeR` in that dataset.

* In the `pointToPoint` notebook, these datasets can be loaded in Python and passed to the `preprocess()` function from the `src.preprocess` module, which will produce a dataset, `nearest_locations` containing the $n$ (usually $n=50$) nearest locations in the right-hand dataset to each location in the left-hand dataset, as the crow flies. Here it is shown with $n=2$:
  unique_code_l|0|1
  ---|---|---
  id_l_1|id_r_a|id_r_b
  id_l_2|id_r_c|id_r_d
  $\vdots$|$\vdots$|$\vdots$

* In the Python function, we then then pivot this table and merge the latitudes and longitudes back in, to get:
  uniqueCodeL|latL|lonL|uniqueCodeR|latR|lonR
  ---|---|---|---|---|---
  id_l_1|50.1|0.2|id_r_a|50.0|0.2
  id_l_1|50.1|0.2|id_r_b|50.2|0.1
  id_l_2|49.1|-2.0|id_r_c|49.1|-1.5
  id_l_2|49.1|-2.0|id_r_d|48.0|-1.9
  
  
* We can use Spark functionality to turn this dataframe into a Spark DataFrame that can be used by both Python and Scala, and the rest of the `pointToPoint` notebook can be run. This notebook calculates the travel times between every pair of locations on each row of this data table, using the OS Multi-Modal Routing Network data and `GraphHopper` package. This script takes several hours to run (though the script can be tested more quickly by setting `runInTestingMode` to be `true` - in this case, the system will only be run for the first 20 locations in the left-hand dataset) This will produce a table with the following schema (shown with $n=2$), and save it to specified location in the config:

  uniqueCodeL|uniqueCodeR|time|distance|transportProfile|sourceDatasetL|sourceDatasetR|lastUpdated
  ---|---|---|---|---|---|---|---
  id_l_1|id_r_a|5.02|0.6|foot_fastest|lsoa_pwcs|pharmacies|2025-05-15 15:30:00
  id_l_1|id_r_b|5.58|0.7|foot_fastest|lsoa_pwcs|pharmacies|2025-05-15 15:30:00
  id_l_2|id_r_c|2.78|0.3|foot_fastest|lsoa_pwcs|pharmacies|2025-05-15 15:30:00
  id_l_2|id_r_d|3.23|0.5|foot_fastest|lsoa_pwcs|pharmacies|2025-05-15 15:30:00
  $\vdots$|$\vdots$|$\vdots$|$\vdots$|$\vdots$|$\vdots$|$\vdots$|$\vdots$

  (times are in minutes, distances are in kilometres)

* The dataset is saved as a partitioned CSV by Scala, and can be opened (in Python) using our `load_partitioned_csv()` function, from `src.read_write_data`.

* Further analysis can now be done using this dataset

Details, including an up-to-date `config.yml`, are available from the Data Science & Applied AI Hub.


## Development status

`pointToPoint.scala` is the main component of interest in this repository, as it takes two datasets and calculates route times between the locations in them. This notebook is in use for several DHSC projects and does not currently have any further development planned.

Example project use cases are in the `projects/` folder.

## QA status

`loadSaveCache.scala`, `pointToPoint.scala`, and `data_cleaning_and_manipulation.py` notebooks have been QA-ed - these notebooks are enough to produce time and distance routing figures for healthcare locations at LSOA level. Results have been compared to the previous dentists analysis and Google Maps figures and compare favourably.

## Getting Help
Please contact datascience@dhsc.gov.uk for more information.

## Code of Conduct
Please note that this project is released with a [Contributor Code of Conduct](https://dhsc-govuk-internal.github.io/user-guide.github.io/code-of-conduct.html). By contributing to this project, you agree to abide by its terms.

### Contributing
`main` branch: All code in the `main` branch must be fully QA-ed, functional, and ready for use.

`dev` branch: The `dev` branch is intended as a working branch, where code is consolidated and undergoes further QA before being merged into main.

### Review

This repository is next scheduled for review on 1 April 2027.
