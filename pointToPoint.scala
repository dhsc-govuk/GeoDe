// Databricks notebook source
// MAGIC %md
// MAGIC # **Point to point calculations**

// COMMAND ----------

// MAGIC %md
// MAGIC This notebook:
// MAGIC - Sets up the GraphHopper (GH) object and reads in the cache of the road data (Ordnance Survey (OS) adjusted version of GH, with turn costs on). In this case, turn costs on means the routing calculation adheres to the rules of the road - one way streets etc.
// MAGIC - Defines a function, _pointToPointCalc_, which returns time and distance between two latitudes and longitudes
// MAGIC - Defines a function, _getTimeDistanceValues_, which runs _pointToPointCalc_ for two lists of points, a 'left' list and a 'right' list. Usually this 'left' list is a list of LSOA centrepoints and the 'right' list is a list of the locations of healthcare locations.
// MAGIC - Reads in (usually) LSOA data
// MAGIC - Reads in healthcare location data
// MAGIC - Creates paired dataset, linking every location from the left-hand dataset to the nearest $n$ (usually 50) right-hand locations as the crow flies.
// MAGIC - Run the point-to-point calculations for all the pairs of locations, create dataframe and save output as a CSV

// COMMAND ----------

// MAGIC %md
// MAGIC ## Set up config and get $n$ nearest locations

// COMMAND ----------

// MAGIC %python
// MAGIC import datetime
// MAGIC import os
// MAGIC from pathlib import Path
// MAGIC
// MAGIC import pandas as pd
// MAGIC from pyspark.sql import SparkSession
// MAGIC
// MAGIC from src.create_spark_session import create_spark_session
// MAGIC from src.preprocess import preprocess
// MAGIC from src.read_write_data import (
// MAGIC     load_config,
// MAGIC     load_partitioned_csv,
// MAGIC     write_dataset,
// MAGIC )
// MAGIC
// MAGIC config: dict = load_config()
// MAGIC
// MAGIC spark_session: SparkSession = create_spark_session("pointToPoint")
// MAGIC
// MAGIC today_datetime: str = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
// MAGIC run_name: str = "_".join(
// MAGIC     [
// MAGIC         config["source_dataset_l_name"],
// MAGIC         config["source_dataset_r_name"],
// MAGIC         config["transport_profile"],
// MAGIC         str(config["number_of_locations_to_use"]),
// MAGIC     ]
// MAGIC )
// MAGIC if config["run_in_testing_mode"]:
// MAGIC     output_folder_name: str = f"test_{run_name}_locations"
// MAGIC else:
// MAGIC     output_folder_name: str = f"results_{run_name}_locations"
// MAGIC
// MAGIC if config["specify_date"]:
// MAGIC     output_folder_name = f"{output_folder_name}_{today_datetime}"
// MAGIC
// MAGIC config["today_datetime"] = today_datetime
// MAGIC if "output_folder_name" not in config:
// MAGIC     config["output_folder_name"] = output_folder_name
// MAGIC
// MAGIC config["output_folder_path"] = os.path.join(
// MAGIC     config["database_path"], config["output_folder_name"]
// MAGIC )
// MAGIC config["relative_output_folder_path"] = f"output/{config['output_folder_name']}"
// MAGIC
// MAGIC # Spark in Scala needs to save to /mnt/... , but Python saves to /dbfs/mnt/... -
// MAGIC # hence this difference
// MAGIC config["point_to_point_output_path"] = os.path.join(
// MAGIC     config["save_directory"], config["output_folder_name"], "point_to_point.csv"
// MAGIC )
// MAGIC
// MAGIC for key, value in config.items():
// MAGIC     spark.conf.set(key, value)

// COMMAND ----------

// MAGIC %python
// MAGIC if not os.path.exists(config["output_folder_path"]):
// MAGIC     os.mkdir(config["output_folder_path"])
// MAGIC if not os.path.exists(config["relative_output_folder_path"]):
// MAGIC     os.mkdir(config["relative_output_folder_path"])

// COMMAND ----------

// MAGIC %python
// MAGIC # Takes about a minute to run
// MAGIC location_pairs_pd_df: pd.DataFrame = preprocess(
// MAGIC     df_l=pd.read_csv(config["dataset_l_file_path"],
// MAGIC                      dtype={"unique_code": 'string'}),
// MAGIC     df_r=pd.read_csv(config["dataset_r_file_path"],
// MAGIC                      dtype={"unique_code": 'string'}),
// MAGIC     n=config["number_of_locations_to_use"],
// MAGIC     max_dist=None,
// MAGIC )
// MAGIC if config["run_in_testing_mode"]:
// MAGIC     location_pairs_pd_df = location_pairs_pd_df.head(
// MAGIC         100 * config["number_of_locations_to_use"]
// MAGIC     )
// MAGIC print("Number of location pairs")
// MAGIC print(location_pairs_pd_df.shape)
// MAGIC
// MAGIC        
// MAGIC location_pairs_pd_df

// COMMAND ----------

// MAGIC %python
// MAGIC location_pairs = spark_session.createDataFrame(location_pairs_pd_df)
// MAGIC location_pairs.write.mode("overwrite").saveAsTable("locationPairs")

// COMMAND ----------

// MAGIC %md
// MAGIC ## Scala Functions

// COMMAND ----------

// imports

import com.graphhopper.{GraphHopper, GHRequest, ResponsePath}
import com.graphhopper.config.{Profile, CHProfile}
import org.apache.spark.sql.{SparkSession, DataFrame}
import org.apache.spark.sql.functions.typedLit
import scala.collection.mutable.ListBuffer
import java.util.Arrays
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

// COMMAND ----------

def createSparkSession(appName: String): SparkSession = {
    val sparkSession = SparkSession
        .builder()
        .appName(appName)
        .getOrCreate()

    return (sparkSession)
}

// COMMAND ----------

/** Read in dataset from a csv
  *
  * @param filePath Path to csv
  * @param sparkSession Current Spark session (should be same as created in Python code)
  * @return DataFrame of the data contained at the specified file path
  */
def readCsv(filePath: String, sparkSession: SparkSession): DataFrame = {
  // Read CSV into a DataFrame
  val df: DataFrame = sparkSession.read
    .option("header", "true")  // Use first row as header
    .option("inferSchema", "true")  // Automatically infer data types
    .csv(filePath)

  return(df)
}

// COMMAND ----------

/** Set up GraphHopper object
  *
  * A GraphHopper object allows us to ascertain travel times between points,
  * which will be defined later.
  *
  * @param hopperLocation Where the GraphHopper should be stored.
  * @param transportProfile What vehicle to calculate for - defaults to "car_fastest".
  * @param setAllowWrites Boolean which specifies if it is allowed for the GraphHopper
  * to write. E.g. for read only filesystems it is not possible to create a lock file
  * and so we can avoid write locks. Defaults to `false`.
  * @param setTurnCosts Turn costs means turn restrictions (like 'left only' or 'no
  * right turn') from OSM will be respected, and U-turns will either be forbidden or
  * there will be a time penalty whenever a route takes a U-turn. Defaults to `true`.
  * @return GraphHopper object with transport type and weighting to use
  */
def setUpHopper(
  hopperLocation: String,
  setAllowWrites: Boolean = false,
  setTurnCosts: Boolean = true
): GraphHopper = {
  val hopper = new GraphHopper()

  hopper.setGraphHopperLocation(hopperLocation)

  hopper.setAllowWrites(setAllowWrites)

  hopper.setProfiles(
    Arrays.asList(
      new Profile("car_fastest").setVehicle("car").setWeighting("fastest").setTurnCosts(setTurnCosts),
      new Profile("bike_fastest").setVehicle("bike").setWeighting("fastest").setTurnCosts(setTurnCosts),
      new Profile("foot_fastest").setVehicle("foot").setWeighting("fastest"),
      new Profile("foot_shortest").setVehicle("foot").setWeighting("shortest")
    )
  )

  hopper.getCHPreparationHandler().setCHProfiles(
    Arrays.asList(
      new CHProfile("car_fastest"),
      new CHProfile("bike_fastest"),
      new CHProfile("foot_fastest"),
      new CHProfile("foot_shortest")
    )
  )

  hopper.load()
  println(s"Successfully loaded GraphHopper object with turn costs set to ${setTurnCosts}")
  return (hopper)
}

// COMMAND ----------

/** Takes two locations and returns the (time, dist) from the first to the second
  *
  * @param pointL x and y coordinate (from)
  * @param pointR x and y coordinate (to)
  * @param hopper GraphHopper object for calculating distances/ travel times between
  * points
  * @param codeL String specifying the code of each centrepoint in the list of
  * locations on the left-hand side, for purposes of logging.
  * @param codeR String specifying the code of each location in the list of
  * locations on the right-hand side, for purposes of logging.
  * @param transportProfile What vehicle to calculate for - defaults to "car_fastest".
  * @return (Double, Double) of time and distance between points
  */
def pointToPointCalc(
  pointL: List[Double],
  pointR: List[Double], 
  hopper: GraphHopper,
  codeL: String,
  codeR: String,
  transportProfile: String = "car_fastest"
): (Double, Double) = {
  
  val (latL, lonL) = (pointL(0), pointL(1))
  val (latR, lonR) = (pointR(0), pointR(1))

  val req = new GHRequest(latL, lonL, latR, lonR).setProfile(transportProfile)

  // Do the routing
  var rsp = new ResponsePath()
  try {
    rsp = hopper.route(req).getBest()
  } catch {
    case e: RuntimeException =>
      println(s"Failed to find route due to: ${e.getMessage}. Error finding route between ($latL, $lonL), location code $codeL, and ($latR, $lonR), location code $codeR.")
      // Exit function early
      return (Double.NaN, Double.NaN)
  }

  // time in mins
  var time = Double.NaN
  try {
    time = rsp.getTime() / (1000 * 60.0)
  } catch {
    case e: RuntimeException =>
      println(s"Failed to get time due to: ${e.getMessage}. Error finding route between ($latL, $lonL), location code $codeL, and ($latR, $lonR), location code $codeR.")
  }

  // Travel distance in kilometres
  var dist = Double.NaN
  try {
    dist = rsp.getDistance() / 1000.0
  } catch {
    case e: RuntimeException =>
      println(s"Failed to get distance due to: ${e.getMessage}. Error finding route between ($latL, $lonL), location code $codeL, and ($latR, $lonR), location code $codeR.")
  }

  return (time, dist)
}

// COMMAND ----------

/** For every location pair, find the times and distances between them
  *
  * @param locationPairs Dataset of journeys
  * @param sourceDatasetLName String, name given to the left hand dataset (usually "lsoa_pwcs")
  * @param sourceDatasetRName String, name given to the right hand dataset
  * @param hopper GraphHopper object for calculating distances/ travel times between
  * points
  * @param sparkSession Current Spark session (should be same as created in Python code)
  * @param transportProfile What vehicle to calculate for - defaults to "car_fastest".
  * @return DataFrame with eight columns - uniqueCodeL, uniqueCodeR, time, distance,
  * transportProfile, sourceDatasetL, sourceDatasetR, lastUpdated
  */
def getResults(
  locationPairs: DataFrame,
  sourceDatasetLName: String,
  sourceDatasetRName: String,
  hopper: GraphHopper,
  sparkSession: SparkSession,
  transportProfile: String = "car_fastest"
): DataFrame = {

  val leftLocationsList = locationPairs.select("latL", "lonL").map(row => List(row.getDouble(0), row.getDouble(1))).collect().toList
  val leftCodesList = locationPairs.select("uniqueCodeL").map(row => row.getString(0)).collect().toList
  val rightLocationsList = locationPairs.select("latR", "lonR").map(row => List(row.getDouble(0), row.getDouble(1))).collect().toList
  val rightCodesList = locationPairs.select("uniqueCodeR").map(row => row.getString(0)).collect().toList

  // Create empty lists to be filled with calculated values
  val times = ListBuffer[Double]()
  val distances = ListBuffer[Double]()

  val numJourneys: Long = locationPairs.count()

  for (((pointL, (codeL, (pointR, codeR))), idx) <- (leftLocationsList zip (leftCodesList zip (rightLocationsList zip rightCodesList))).zipWithIndex){
    printf(s"\r${idx+1}/${numJourneys}")
    val (time, distance) = pointToPointCalc(pointL, pointR, hopper, codeL, codeR, transportProfile)
    times += time
    distances += distance
  }
  println("[Done]")

  // Make a dataframe of results
  // Convert each ListBuffer to a List
  val data = Seq(
    leftCodesList,
    rightCodesList,
    times.toList,
    distances.toList
    // Lats and lons can be  found using a lookup, so have removed from this table
  ).transpose

  // Define column names
  // Lats and lons can be  found using a lookup, so have removed from this table
  val columns = Seq("uniqueCodeL", "uniqueCodeR", "time", "distance")

  // Convert to DataFrame by mapping each row to a tuple and then calling toDF
  val dfResults: DataFrame = data.map {
    // Lats and lons can be  found using a lookup, so have removed from this table
    case List(uniqueCodeL: String, uniqueCodeR: String, time: Double, distance: Double) =>
      (uniqueCodeL, uniqueCodeR, time, distance)
  }.toDF(columns: _*).orderBy("uniqueCodeL", "time").withColumns(
    Map(
      "transportProfile" -> typedLit(transportProfile),
      "sourceDatasetL" -> typedLit(sourceDatasetLName),
      "sourceDatasetR" -> typedLit(sourceDatasetRName),
      "lastUpdated" -> typedLit(LocalDateTime.now())
    )
  )
  println("Got results from point-to-point analysis")
  println(s"Number of rows: ${dfResults.count()}")
  
  return (dfResults)
}

// COMMAND ----------

/** Conduct full point to point analysis
  *
  * @param hopperLocation Where the GraphHopper should be stored.
  * @param locationPairs DataFrame containing columns uniqueCodeL, latL, lonL, uniqueCodeR, latR,
  * lonR - each row is a journey that we want to get the time and distance of
  * @param sourceDatasetLName String, name given to the left hand dataset (usually "lsoa_pwcs")
  * @param sourceDatasetRName String, name given to the right hand dataset
  * @param sparkSession Current Spark session (should be same as created in Python code)
  * @param transportProfile What vehicle to calculate for - defaults to "car_fastest". Can also
  * be "foot_fastest", "foot_shortest", or "bike_fastest".
  * @param setAllowWrites Boolean which specifies if it is allowed for the GraphHopper
  * to write. E.g. for read only filesystems it is not possible to create a lock file
  * and so we can avoid write locks. Defaults to `false`.
  * @param setTurnCosts Turn costs means turn restrictions (like 'left only' or 'no
  * right turn') from OSM will be respected, and U-turns will either be forbidden or
  * there will be a time penalty whenever a route takes a U-turn. Defaults to `true`.
  * @return DataFrame with eight columns - uniqueCodeL, uniqueCodeR, time, distance,
  * transportProfile, sourceDatasetL, sourceDatasetR, lastUpdated
  */
def pointToPointAnalysis(
  hopperLocation: String,
  locationPairs: DataFrame,
  sourceDatasetLName: String,
  sourceDatasetRName: String,
  sparkSession: SparkSession,
  transportProfile: String = "car_fastest",
  setAllowWrites: Boolean = false,
  setTurnCosts: Boolean = true
): DataFrame = {

  val hopper: GraphHopper = setUpHopper(
    hopperLocation = hopperLocation,
    setAllowWrites = setAllowWrites,
    setTurnCosts = setTurnCosts
  )

  val results: DataFrame = getResults(
    locationPairs = locationPairs,
    sourceDatasetLName = sourceDatasetLName,
    sourceDatasetRName = sourceDatasetRName,
    hopper = hopper,
    sparkSession = sparkSession,
    transportProfile = transportProfile
  )

  return (results)
}

// COMMAND ----------

/** Writes DataFrame to a csv file of the form `saveDirectory/datasetName_{date}.csv`
  *
  * @param df DataFrame
  * @param datasetPath Path (ending .csv) to which to save the output.
  */
def writeDataToCsv(df: DataFrame, datasetPath: String): Unit = {
  df.write
    .option("header", "true")
    .mode("overwrite") // Write the header
    .csv(datasetPath)

  println(s"Successfully saved travel times and distances to ${datasetPath}")
}

// COMMAND ----------

// MAGIC %md
// MAGIC ## Run Scala System

// COMMAND ----------

val sparkSession: SparkSession = createSparkSession("pointToPoint")
val dfResults: DataFrame = pointToPointAnalysis(
  hopperLocation = spark.conf.get("graphDbfsStorage"),
  locationPairs = sparkSession.read.table("locationPairs"),
  sourceDatasetLName = spark.conf.get("source_dataset_l_name"),
  sourceDatasetRName = spark.conf.get("source_dataset_r_name"),
  sparkSession = sparkSession,
  transportProfile = spark.conf.get("transport_profile")
)
dfResults.show()

// COMMAND ----------

writeDataToCsv(
  df = dfResults,
  datasetPath = spark.conf.get("point_to_point_output_path")
)

// COMMAND ----------

// MAGIC %python
// MAGIC df_results = load_partitioned_csv(f"/dbfs{config['point_to_point_output_path']}")
// MAGIC display(df_results)
// MAGIC relative_output_path = Path(config["relative_output_folder_path"]) / "point_to_point.csv"
// MAGIC write_dataset(df_results, relative_output_path, specify_date=False)
// MAGIC print(f"Saved to {relative_output_path}")

// COMMAND ----------

// MAGIC %md
// MAGIC ## Extracting routes

// COMMAND ----------

/** Takes two locations and returns the notes on the route between them
  *
  * @param pointL x and y coordinate (from)
  * @param pointR x and y coordinate (to)
  * @param hopper GraphHopper object for calculating distances/ travel times between
  * points
  * @param codeL String specifying the code of each centrepoint in the list of
  * locations on the left-hand side, for purposes of logging.
  * @param codeR String specifying the code of each location in the list of
  * locations on the right-hand side, for purposes of logging.
  * @param transportProfile What vehicle to calculate for - defaults to "car_fastest".
  * @return String All nodes on route as a string
  */
def getRoute(
  pointL: List[Double],
  pointR: List[Double], 
  hopper: GraphHopper,
  codeL: String,
  codeR: String,
  transportProfile: String = "car_fastest"
): String = {
  
  val (latL, lonL) = (pointL(0), pointL(1))
  val (latR, lonR) = (pointR(0), pointR(1))

  val req = new GHRequest(latL, lonL, latR, lonR).setProfile(transportProfile)

  // Do the routing
  var rsp = new ResponsePath()
  var route = new String
  try {
    rsp = hopper.route(req).getBest()
    route = rsp.getPoints().toString()
  } catch {
    case e: RuntimeException =>
      println(s"Failed to find route due to: ${e.getMessage}. Error finding route between ($latL, $lonL), location code $codeL, and ($latR, $lonR), location code $codeR.")
      // Exit function early
      return ""
  }
 
  return route
}

// COMMAND ----------

/** For every location pair, find the times and distances between them
  *
  * @param locationPairs Dataset of journeys
  * @param hopper GraphHopper object for calculating distances/ travel times between
  * points
  * @param transportProfile What vehicle to calculate for - defaults to "car_fastest".
  * @return DataFrame with three columns - uniqueCodeL, uniqueCodeR, route
  */
def getRoutesForDataFrame(
  locationPairs: DataFrame,
  hopper: GraphHopper,
  transportProfile: String = "car_fastest"
): DataFrame = {

  val leftLocationsList = locationPairs.select("latL", "lonL").map(row => List(row.getDouble(0), row.getDouble(1))).collect().toList
  val leftCodesList = locationPairs.select("uniqueCodeL").map(row => row.getString(0)).collect().toList
  val rightLocationsList = locationPairs.select("latR", "lonR").map(row => List(row.getDouble(0), row.getDouble(1))).collect().toList
  val rightCodesList = locationPairs.select("uniqueCodeR").map(row => row.getString(0)).collect().toList

  // Create empty list to be filled with calculated values
  val routes = ListBuffer[String]()

  val numJourneys: Long = locationPairs.count()

  for (((pointL, (codeL, (pointR, codeR))), idx) <- (leftLocationsList zip (leftCodesList zip (rightLocationsList zip rightCodesList))).zipWithIndex){
    printf(s"\r${idx+1}/${numJourneys}")
    val route: String = getRoute(pointL, pointR, hopper, codeL, codeR, transportProfile)
    routes.append(route)
  }
  println("[Done]")

  val data = Seq(
    leftCodesList,
    rightCodesList,
    routes.toList
    // Lats and lons can be  found using a lookup, so have removed from this table
  ).transpose

  // Define column names
  // Lats and lons can be  found using a lookup, so have removed from this table
  val columns = Seq("uniqueCodeL", "uniqueCodeR", "route")

  // Convert to DataFrame by mapping each row to a tuple and then calling toDF
  val pairsWithRoutes: DataFrame = data.map {
    // Lats and lons can be  found using a lookup, so have removed from this table
    case List(uniqueCodeL: String, uniqueCodeR: String, route: String) =>
      (uniqueCodeL, uniqueCodeR, route)
  }.toDF(columns: _*).orderBy("uniqueCodeL")
  println("Got routes")
  println(s"Number of rows: ${locationPairs.count()}")
  
  return (pairsWithRoutes)
}
