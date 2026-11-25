from pyspark.sql import SparkSession


def create_spark_session(app_name: str, master: str = "local[*]") -> SparkSession:
    """Create Spark session with a particular name, so that data can be passed between
    languages.

    Args:
        app_name (str): Name of folder to output to
        master (str): Spark master URL to connect to ("local" to run locally, "local[*]" to run
        locally with all cores, "local[4]" for four cores, etc.). Defaults to "local[*]"

    Returns:
        SparkSession: Spark Session object
    """
    spark_session = (
        SparkSession
        .builder
        .appName(app_name)
        .master(master)
        .getOrCreate()
    )
    return spark_session
