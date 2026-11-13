# DDRM – Page-wise Features with Explicit DSA Visibility

This document describes the DDRM website **page by page**, where each page is intentionally designed to **visually and functionally expose specific data structures and algorithms**.  
There is no separate DSA debug page — the system itself demonstrates DSA concepts naturally through interaction.

---

## 1. Map & Simulation Page (Flood Simulation View)

This page visualizes disaster spread and directly exposes the flood algorithm.

### Features
- Display real-world map of Pattangere using Leaflet
- Render all zones as polygons from GeoJSON
- Render river zones distinctly
- Start flood simulation by clicking a river zone
- Flood spreads step-by-step across adjacent zones
- Zones gradually turn blue based on flood progression

### What the User Sees (DSA Visibility)
- Flood spreads outward level by level
- Flood does NOT jump randomly
- Only adjacent zones are affected per step

This makes **Breadth-First Search behavior visually obvious**.

### DSA Used
- **Graph**: Zones as nodes, adjacency as edges
- **Queue (BFS)**: Flood propagation frontier
- **Hash Map**: Zone state lookup and updates

---

## 2. Public / Reporter Mode Page

This page demonstrates structured data input and FIFO processing.

### Features
- Location search bar with auto-complete
- Map click support for selecting location
- Simple report submission form

### Report Types (STRICT)
Only two report types exist:
- **Flood**
- **Rescue**

#### Flood Report
- Zone-based (user selects a zone)
- Boolean (flooded = yes)
- Immediately marks the zone as flooded

#### Rescue Report
- Zone-based
- Contains only:
  - Number of people needing rescue

### What the User Sees (DSA Visibility)
- Auto-complete suggestions appear while typing
- Reports appear in the order they were submitted

### DSA Used
- **Trie**: Location search and auto-complete
- **Queue**: Incoming reports buffered in FIFO order
- **Hash Map**: Report storage and zone lookup

---

## 3. Rescue Centre Page

This page is explicitly designed to contrast **Queue vs Priority Queue** side by side.

### Layout
- Left panel: Unverified rescue reports
- Right panel: Priority rescue list

---

### 3.1 Unverified Rescue Reports (Queue View)

### Features
- Displays rescue reports in arrival order
- Each report has a “Verify” button

### What the User Sees (DSA Visibility)
- Oldest report always at the top
- New reports appear at the bottom

This makes **FIFO queue behavior obvious**.

### DSA Used
- **Queue**
  - Preserves arrival order
  - No prioritization yet

---

### 3.2 Verified Rescue Requests (Priority Queue View)

### Features
- Verified rescue reports move here
- Automatically sorted by number of people
- Highest-priority rescue always appears first

### Priority Rule
- Priority = number of people needing rescue
- No distance or time complexity added

### What the User Sees (DSA Visibility)
- Reports reorder automatically after verification
- Larger rescue requests rise to the top

This makes **heap-based prioritization clearly visible**.

### DSA Used
- **Priority Queue (Max Heap)**

---

## 4. Active Rescue Missions Page

This page demonstrates dynamic data structures and routing.

### Features
- Multiple rescue teams shown
- Each team has a fixed capacity (e.g., 20 people)
- Drag-and-drop rescue requests onto teams
- Prevents assignment beyond team capacity
- Button to start rescue operations

### Mission Execution
- Rescue teams move along computed routes
- Movement is animated in real time
- Teams automatically return after capacity is filled

### What the User Sees (DSA Visibility)
- Rescue tasks appear as an ordered list per team
- Tasks can be added or removed dynamically
- Order of execution is visible

### DSA Used
- **Linked List**
  - Stores sequence of rescue missions per team
  - Supports dynamic insertion/removal
- **Graph**
  - Used to compute rescue routes

---

## 5. Dynamic Rerouting During Rescue

This behavior occurs live during rescue operations.

### Trigger Conditions
- Flood spreads into:
  - A zone on the active route
  - A road used by the route

### Behavior
- Current route becomes unsafe
- System backtracks to the last safe zone
- A new route is computed and displayed

### What the User Sees (DSA Visibility)
- Route partially disappears
- New route replaces unsafe section
- Rescue continues without restarting

### DSA Used
- **Stack**
  - Stores the current route path
  - Pops unsafe segments
- **Graph + Dijkstra / A***
  - Recomputes shortest safe route

---

## 6. Implicit DSA Demonstration Philosophy

The system avoids artificial debug screens.

Instead:
- Flood spread shows BFS naturally
- Rescue queues show FIFO vs priority behavior
- Routing and rerouting show stack + graph logic
- Mission chaining shows linked list behavior

This ensures:
- Intuitive understanding for examiners
- No ambiguity about where DSA is applied
- Strong academic defensibility

---

## Summary: Page → DSA Mapping

| Page | DSA Clearly Visible |
|----|---------------------|
| Map & Simulation | Graph, BFS Queue |
| Reporter Mode | Trie, Queue |
| Rescue Queue | Queue |
| Priority Rescue | Priority Queue |
| Active Missions | Linked List |
| Live Rerouting | Stack, Graph |

---

This design ensures that **every interaction on the website corresponds directly to a data structure**, making the project easy to demonstrate, explain, and evaluate.
