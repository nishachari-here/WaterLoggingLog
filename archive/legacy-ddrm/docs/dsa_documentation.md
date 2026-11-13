# Data Structures and Algorithms (DSA) Documentation

This document provides a comprehensive overview of the data structures and algorithms implemented in the Dynamic Disaster Response Mapper (DDRM).

---

## 1. Graph (Adjacency List)
**Location:** [`dsa-engine/src/main.cpp:15`](file:///d:/Documents/College/Disaster-Response-mapper/dsa-engine/src/main.cpp#L15)
- **Implementation:** `std::unordered_map<std::string, std::vector<std::string>> adjacency`
- **Usage:** Stores the disaster zones as nodes and their physical connections (land or river) as edges. This is the "map" that the algorithms navigate.
- **Complexity:**
  - **Space Complexity:** $O(V + E)$ where $V$ is number of zones and $E$ is number of edges.
  - **Time Complexity (Access):** $O(1)$ average time to retrieve neighbors of any zone.

---

## 2. Breadth-First Search (BFS)
**Location:** [`dsa-engine/src/main.cpp:49`](file:///d:/Documents/College/Disaster-Response-mapper/dsa-engine/src/main.cpp#L49)
- **Implementation:** Manual step-by-step BFS using a `std::queue` and `std::unordered_set`.
- **Usage:** Powers the **Flood Simulation**. It ensures that water spreads level-by-level (layer-by-layer) to all adjacent connected zones.
- **Complexity:**
  - **Time Complexity:** $O(V + E)$ as each zone and connection is processed exactly once.

---

## 3. Queue (FIFO)
**Locations:**
- **Engine (BFS):** [`dsa-engine/src/main.cpp:18`](file:///d:/Documents/College/Disaster-Response-mapper/dsa-engine/src/main.cpp#L18) - `std::queue<std::string> floodQueue`.
- **Frontend (Reports):** [`frontend/DDRM/src/pages/ReporterMode.jsx:8`](file:///d:/Documents/College/Disaster-Response-mapper/frontend/DDRM/src/pages/ReporterMode.jsx#L8) - `const [reports, setReports] = useState([])`.
- **Usage:**
  - **Engine:** Maintains the "frontier" of the flood.
  - **Frontend:** Manages incoming disaster reports in the exact order they were received (First-In, First-Out).
- **Complexity:**
  - **Time Complexity:** $O(1)$ for Enqueue (push) and Dequeue (pop) operations.

---

## 4. Priority Queue (Max-Heap)
**Location:** [`frontend/DDRM/src/pages/AuthorityMode.jsx:14`](file:///d:/Documents/College/Disaster-Response-mapper/frontend/DDRM/src/pages/AuthorityMode.jsx#L14)
- **Implementation:** Simulated using Array sorting: `[...reports].sort((a, b) => b.priority - a.priority)`.
- **Usage:** Used in **Authority Mode** to prioritize rescue missions. The zone with the highest number of stranded people (highest priority) is moved to the top of the queue.
- **Complexity:**
  - **Time Complexity:** $O(N \log N)$ per update in the current React implementation. In a standard Heap implementation, this would be $O(\log N)$ for insertion/deletion.

---

## 5. Linked List
**Location:** [`frontend/DDRM/src/pages/AuthorityMode.jsx:54`](file:///d:/Documents/College/Disaster-Response-mapper/frontend/DDRM/src/pages/AuthorityMode.jsx#L54)
- **Implementation:** Visualized as a chain of nodes in the Mission Dashboard.
- **Usage:** Represents **Active Mission Chains**. Rescue teams follow a sequential list of zones to visit, where each node in the mission chain points to the next location.
- **Complexity:**
  - **Time Complexity:** $O(1)$ for adding/removing mission checkpoints at the head/tail.

---

## 6. Hash Set
**Location:** [`dsa-engine/src/main.cpp:17`](file:///d:/Documents/College/Disaster-Response-mapper/dsa-engine/src/main.cpp#L17)
- **Implementation:** `std::unordered_set<std::string> floodedZones`
- **Usage:** Used within the BFS engine to keep track of **visited** zones. This prevents the simulation from entering infinite loops or re-processing the same zone multiple times.
- **Complexity:**
  - **Time Complexity:** $O(1)$ average for checking if a zone is already flooded (`find`) and for marking it as flooded (`insert`).

---

## 7. Hash Map (Dictionary)
**Location:** [`dsa-engine/src/main.cpp:15-16`](file:///d:/Documents/College/Disaster-Response-mapper/dsa-engine/src/main.cpp#L15)
- **Implementation:** `std::unordered_map`
- **Usage:** Maps Zone IDs (Strings like "1" or "r2") to their properties (Adjacent zones list and Capacity).
- **Complexity:**
  - **Time Complexity:** $O(1)$ average for data retrieval.

---

## 8. Stack (Implied/Planned)
**Reference:** `README.md`
- **Concept:** Used for **Route Backtracking**. If a rescue team finds a blocked path, they pop previously visited checkpoints from the stack to return to the last safe intersection and reroute.
- **Complexity:**
  - **Time Complexity:** $O(1)$ for Push and Pop.
