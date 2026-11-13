# DDRM Zones, Graph Model, and Website Modes

This document defines the **zone structure**, **flood graph**, and **website modes** used in the Dynamic Disaster Response Mapper (DDRM).

---

## 1. Geographic Zoning Model

### Area
- Pattangere, Bengaluru
- Includes the Vrishabhavathi river

### Zone Types
- **Normal Zones**: Residential / road areas
- **River Zones (rzones)**: Flood source zones

### Zone Identifiers
- Normal zones: `zone1` → `zone18`
- River zones: `rzone1` → `rzone6`

---

## 2. Adjacency Graph (Flood & Routing)

### Zone Adjacency List

zone1 -> zone2
zone2 -> zone1, zone3
zone3 -> zone2, zone4, zone5, rzone1
zone4 -> zone3, zone6, zone5, rzone2
zone5 -> zone3, zone4, zone7
zone6 -> zone4, zone7, zone8, rzone3
zone7 -> zone5, zone6, zone9
zone8 -> zone6, zone9, zone10
zone9 -> zone7, zone8
zone10 -> zone8, rzone5, rzone6
zone11 -> zone12, zone13
zone12 -> rzone1, rzone2, zone11, zone14
zone13 -> zone11, zone14, zone15
zone14 -> zone12, zone13, zone16, rzone3
zone15 -> zone13, zone16, zone17
zone16 -> zone14, zone15, zone18, rzone4, rzone5
zone17 -> zone15, zone18
zone18 -> zone16, zone17, rzone6

rzone1 -> zone3, zone12
rzone2 -> zone4, zone12
rzone3 -> zone6, zone14
rzone4 -> zone6, zone16
rzone5 -> zone10, zone16
rzone6 -> zone10, zone18


### Design Rationale
- Each river zone connects to **exactly two zones**
- Flood enters city through controlled entry points
- Ensures realistic and explainable BFS behavior

---

## 3. Flood Simulation Logic

### Flood Sources
- Any river zone selected by admin
- Can be multiple simultaneous sources

### Propagation
- BFS traversal
- Discrete time steps
- Threshold-based spillover

### Data Structures
- Queue for BFS
- Hash map for zone state
- Graph adjacency list

---

## 4. Website Modes

### Mode 1: Public / Reporter Mode

**Who**: Any user / citizen  
**Goal**: Submit disaster reports

#### Features
- Location search (Trie)
- Map click selection
- Simple report form

#### Report Types
- Flood (zone-based)
- Rescue (people count)

This is the entry point for crowdsourced data.

---

### Mode 2: Simulation / Control Mode

**Who**: Admin / demo operator  
**Goal**: Control flood simulation

#### Features
- Select river zones
- Start / pause flood
- Advance time step
- Visualize flood spread

#### Algorithms
- BFS flood propagation
- Queue visualization

---

### Mode 3: Response / Authority Mode

**Who**: Disaster response authority  
**Goal**: Coordinate rescues

#### Features
- View incoming rescue queue
- Verify reports
- Priority-based rescue list
- Generate rescue routes
- Monitor live missions

#### Algorithms & DS
- Queue → Priority Queue
- Graph routing
- Stack-based rerouting
- Linked list missions

---

### Mode 4: DSA Debug Mode (Optional)

**Who**: Examiner / evaluator  
**Goal**: Explicit DSA demonstration

#### Features
- Show active data structures
- Display sizes and contents
- Highlight algorithm steps
- Pause and inspect state

This mode maximizes academic value.

---

## 5. UI-to-DSA Mapping Summary

| UI Action | Data Structure |
|---------|---------------|
| Submit report | Queue |
| Verify rescue | Priority Queue |
| Search location | Trie |
| Flood spread | BFS + Queue |
| Route planning | Graph + PQ |
| Route failure | Stack |
| Mission tracking | Linked List |

---

## Conclusion

This zoning and mode-based design ensures:
- Clear separation of concerns
- Easy demonstration of DSA concepts
- Realistic disaster simulation
- Strong academic defensibility
