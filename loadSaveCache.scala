// Databricks notebook source
// MAGIC %md
// MAGIC ## Create cache of road network data

// COMMAND ----------

// MAGIC %md
// MAGIC This notebook:
// MAGIC - Reads in GraphHopper and the Ordnance Survey road network data
// MAGIC - Creates a cache of the road network data with the car, bike, and foot profiles selected and turn costs on.
// MAGIC
// MAGIC Be prepared for it to take a few hours to run in full! Previous runs have taken two and a half hours.

// COMMAND ----------

// MAGIC %python
// MAGIC import os
// MAGIC
// MAGIC from src.read_write_data import load_config
// MAGIC
// MAGIC config: dict = load_config()
// MAGIC for key, value in config.items():
// MAGIC     spark.conf.set(key, value)
// MAGIC     if key in ["pbfDbfsStorage", "graphDbfsStorage", "graphLocalStorage"]:
// MAGIC         os.environ[key] = spark.conf.get(key)

// COMMAND ----------

import com.graphhopper.GraphHopper
import com.graphhopper.config.Profile
import com.graphhopper.config.CHProfile
import java.util.Arrays


/** Load and save cache
  *
  * Reads in GraphHopper and the Ordnance Survey road network data
  * Creates a cache of the road network data with the a specific profile
  * selected and turn costs on or off optionally.
  *
  * @param pbfDbfsStorage String, file path pointing to where the routing tool data
  * are stored (a .pbf file)
  * @param graphDbfsStorage String, file path to save the output on DBFS
  * @param graphLocalStorage String, file path to save the output on local disk
  * @param setTurnCosts Turn costs means turn restrictions (like 'left only' or 'no
  * right turn') from OSM will be respected, and U-turns will either be forbidden or
  * there will be a time penalty whenever a route takes a U-turn. Defaults to `true`.
  */
def loadSaveCache(
  pbfDbfsStorage: String,
  graphDbfsStorage: String,
  graphLocalStorage: String,
  setTurnCosts: Boolean = true
) = {
  val hopper = new GraphHopper()

  println("Setting OSM file for GraphHopper object")
  hopper.setOSMFile(pbfDbfsStorage)
  println("Setting location for GraphHopper object")
  hopper.setGraphHopperLocation(graphLocalStorage)

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

  hopper.importAndClose()
  hopper.close()
  println("Loaded and saved cache for GraphHopper")
}

// COMMAND ----------

loadSaveCache(
  pbfDbfsStorage = spark.conf.get("pbfDbfsStorage"),
  graphDbfsStorage = spark.conf.get("graphDbfsStorage"),
  graphLocalStorage = spark.conf.get("graphLocalStorage")
)

// COMMAND ----------

// MAGIC %md
// MAGIC Copy the cache into DBFS.

// COMMAND ----------

// MAGIC %sh
// MAGIC
// MAGIC mkdir -p $graphDbfsStorage
// MAGIC cp -r $graphLocalStorage/* $graphDbfsStorage/

// COMMAND ----------

// MAGIC %sh 
// MAGIC
// MAGIC ls -al $graphDbfsStorage/

// COMMAND ----------

// MAGIC %sh
// MAGIC ls $graphLocalStorage
