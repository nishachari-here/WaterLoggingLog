"""Builds the network layer: OSM roads/drains/lakes -> directed drain graph. Run after run_terrain.py.

    .venv\\Scripts\\python run_network.py
    .venv\\Scripts\\streamlit run app.py
"""
from pipeline import drain_graph, osm
from pipeline.risk import DrainModel


def main():
    print("[1/3] OpenStreetMap layers")
    g = osm.roads()
    print(f"  roads {g.number_of_nodes()} nodes / {g.number_of_edges()} edges, "
          f"{len(osm.waterways())} waterways, {len(osm.waterbodies())} water bodies")
    print("[2/3] drain graph")
    drain_graph.build()
    print("[3/3] hotspot thresholds at 20% blockage")
    m = DrainModel()
    t = m.thresholds({"default": 0.2})[["name", "i_crit_mm_h", "bottleneck_label", "capacity_source"]]
    print(t.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
