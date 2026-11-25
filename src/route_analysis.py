import re


def route_str_to_list(route_str: str) -> list[tuple[float, float]]:
    """
    Given a string of node latitudes and longitudes, returns a list of tuples.

    Arguments:
        route_str (str): String such as "(51.3,-2.1), (51.4,-2.2)"

    Returns:
        list[tuple[float, float]]: List such as [(51.3,-2.1), (51.4,-2.2)]
    """
    location_str_pairs: list[str] = re.findall(
        r"\([0-9\.]+,\s?-?[0-9\.]+\)", route_str
    )

    nodes: list[tuple[float, float]] = [
        tuple(float(k) for k in re.findall(r"-?[0-9\.]+", location_str_pair))
        for location_str_pair in location_str_pairs
    ]
    return nodes
