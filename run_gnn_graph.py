"""Build a typed road-and-drainage graph with DEM features for graph-learning experiments.

    .venv\\Scripts\\python run_terrain.py
    .venv\\Scripts\\python run_gnn_graph.py
"""
from pipeline import combined_graph, drain_graph, osm


def main():
    print("[1/3] DEM-derived drainage graph (no hand-listed hotspot nodes)")
    drains = drain_graph.build()
    print("[2/3] Full drivable OSM graph (includes local streets)")
    roads = osm.all_roads()
    print(f"  roads {roads.number_of_nodes()} nodes / {roads.number_of_edges()} edges")
    print("[3/3] Combine networks and sample DEM features")
    graph = combined_graph.build(roads, drains)
    edge_types = {}
    for _, _, data in graph.edges(data=True):
        edge_types[data["edge_type"]] = edge_types.get(data["edge_type"], 0) + 1
    print(f"  combined graph {graph.number_of_nodes()} nodes / {graph.number_of_edges()} edges")
    print(f"  edges by type: {edge_types}")
    print(f"  wrote {combined_graph.NODES_PATH}")
    print(f"  wrote {combined_graph.EDGES_PATH}")
    print(f"  wrote {combined_graph.GRAPH_PATH}")


if __name__ == "__main__":
    main()
