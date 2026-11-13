# Dynamic Disaster Response Mapper (DDRM)
## Feature Specification Document

This document describes the complete feature set of the Dynamic Disaster Response Mapper (DDRM) with a strong emphasis on **data structure usage and algorithmic clarity**. The system is intentionally designed to demonstrate how classical DSA concepts solve real-world disaster response problems.

---

## 1. Disaster Simulation (Flood)

### Overview
The system simulates flood propagation over a real geographic area divided into zones. Flood spread is deterministic, step-based, and visually observable on the map.

### Representation
- City is divided into **zones**
- Zones form a **graph**
- Some zones are marked as **river zones** (flood sources)

Each zone stores:
- Zone ID
- Water capacity (threshold)
- Current water level
- Flooded status (boolean)

### Algorithm
- **Breadth-First Search (BFS)** using a **Queue**
- Flood starts from river zones
- At each time step:
  - Water level increases
  - If threshold is crossed → neighbors are flooded

### Why BFS?
- Flood spreads uniformly outward
- Time-step based propagation
- Easy to visualize and explain in demos

---

## 2. User Reporting System

### Overview
Users can submit reports that contribute to disaster awareness. Reports are intentionally simple to ensure clean data and easy algorithmic processing.

### Report Types
Only two types are supported:
- **Flood Report**
- **Rescue Report**

### Flood Report
- Indicates a zone is flooded
- Automatically marks the zone as flooded
- Triggers route re-evaluation

### Rescue Report
- Indicates trapped people
- Contains number of people
- Used for rescue prioritization

### Mandatory Fields
- Location (zone)
- Report type (Flood / Rescue)

### Optional Fields
- Number of people (for rescue only)

### Data Structure Usage
- **Queue**: Incoming reports are buffered in FIFO order
- **Priority Queue (Heap)**: Verified rescue reports are ranked by number of people

---

## 3. Rescue Task Prioritization

### Overview
Rescue operations are prioritized based on urgency.

### Priority Logic
- Priority = number of people affected
- Larger groups → higher priority

### Algorithm & DS
- **Priority Queue (Max Heap)**
- Allows efficient extraction of most urgent rescue

### Why not distance/time?
- Keeps logic simple and explainable
- Focus stays on DSA concepts, not optimization math

---

## 4. Rescue Routing & Rerouting

### Route Planning
- Zones are graph nodes
- Roads are edges
- Edge weights represent traversal cost

### Algorithms Used
- **Dijkstra / A*** for shortest/safest path
- **Priority Queue** internally for routing

### Dynamic Rerouting
If a route becomes unsafe due to flooding:
- Use a **Stack** to backtrack to the last safe zone
- Re-run shortest path from that point

### Why Stack?
- Natural LIFO behavior for undoing unsafe paths
- Demonstrates realistic backtracking logic

---

## 5. Active Rescue Missions

### Overview
Each rescue team can be assigned multiple rescue tasks sequentially.

### Data Structure
- **Linked List**
- Each node represents a rescue task
- Supports:
  - O(1) insertion
  - Dynamic reassignment

### Capacity Constraint
- Each team has a fixed rescue capacity (e.g., 20 people)
- New tasks rejected once capacity is exceeded

---

## 6. Location Search

### Overview
Users can search for locations by name when submitting reports.

### Algorithm
- **Trie**
- Auto-completes location names based on prefix

### Why Trie?
- Search time depends on word length, not dataset size
- Fast and intuitive under pressure

---

## 7. Real-Time Visualization

### Features
- Flooded zones turn blue
- Flood intensity changes with time
- Rescue routes update live
- Rerouting visibly occurs

### Communication
- WebSockets (Socket.IO)
- Backend pushes updates to frontend instantly

---

## 8. DSA Debug Mode (High-Scoring Feature)-not a mode per say it'll be part of everything to make it easy to see data structures

### Purpose
Explicitly expose DSA internals during demo/viva.

### Visible Metrics
- Queue size (reports, BFS)
- Heap contents (rescue priority)
- Current BFS frontier
- Active route stacks
- Graph edge status

### Benefit
Prevents assumptions like:
> “Database handled everything”

---

## Summary of Data Structures Used

| Data Structure | Purpose |
|---------------|--------|
| Graph | Zones & road network |
| Queue | Flood BFS, report buffering |
| Priority Queue | Rescue prioritization |
| Stack | Route backtracking |
| Hash Map | Zone & report lookup |
| Linked List | Active missions |
| Trie | Location search |

---

This feature set is intentionally minimal, realistic, and **DSA-first**, ensuring the system is easy to build, demonstrate, and defend academically.
