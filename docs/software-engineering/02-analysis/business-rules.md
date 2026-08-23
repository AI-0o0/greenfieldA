# 05. Agricultural Domain Business Rules

Extracted directly from database constraints, SOP documents, and environment checks:

---

## 1. Environmental & Regulatory Buffer Rules
- **BR-CHEM-01 (Canal Proximity Buffer)**: Restricted chemical spraying is prohibited within **15 meters** of waterways, canals, or irrigation channels ([`agent/algorithms/environment.py:39-47`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L39-L47), [`mcp_server/server.py:55`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L55)). Controlled chemicals require an **8 meter** buffer.
- **BR-CHEM-02 (Organic Neighbor Drift Buffer)**: Mandatory **50 meter** drift buffer zone required when spraying adjacent to certified organic plots ([`agent/algorithms/environment.py:49-56`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L49-L56)).
- **BR-CHEM-03 (Wind Speed Limit)**: Spraying restricted or controlled chemicals is illegal when sustained wind speeds exceed **15 km/h** ([`agent/algorithms/environment.py:58-65`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L58-L65), [`mcp_server/server.py:62`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L62)).
- **BR-CHEM-04 (Midday Heat Spray Ban)**: Spraying during temperatures over **35°C** (e.g. 38°C midday advisory) is banned due to rapid evaporation; dispatches must be split into morning (06:00-09:00) or evening (17:00-20:00) windows ([`agent/algorithms/environment.py:67-74`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L67-L74)).

---

## 2. Fleet & Machinery Mechanical Rules
- **BR-FLEET-01 (Soil Compaction Restriction)**: Heavy equipment (e.g. 8-wheel tractor `TRC-205`) is prohibited on fields with high clay moisture (> 35%) to avoid root zone compaction; lightweight tractors (`TRC-201`) must be substituted ([`agent/algorithms/environment.py:76-84`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L76-L84), [`rag/docs/equipment_manuals.txt:12`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/docs/equipment_manuals.txt#L12)).
- **BR-FLEET-02 (Sprayer Operating Speed Limit)**: Maximum operating speed for sprayers carrying restricted chemicals must not exceed **12 km/h** ([`rag/docs/equipment_manuals.txt:4`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/docs/equipment_manuals.txt#L4)).
- **BR-FLEET-03 (Sprayer Pressure Calibration)**: Standard flow calibration requires nozzle pressure maintained at **30 PSI**; out-of-spec sprayers (e.g. 22 PSI) must be routed to the shop for recalibration ([`agent/algorithms/environment.py:86-94`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L86-L94), [`rag/docs/equipment_manuals.txt:34`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/docs/equipment_manuals.txt#L34)).
- **BR-FLEET-04 (Harvester Power Line Clearance)**: Clearance height under overhead power lines must be at least **4 meters** ([`rag/docs/equipment_manuals.txt:39`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/docs/equipment_manuals.txt#L39)).

---

## 3. Financial & Customer Operational Rules
- **BR-FIN-01 (Credit Hold Blockade)**: No equipment may be dispatched to a customer with `credit_hold = 1` until outstanding payments are processed ([`mcp_server/tools.py:133`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L133), [`agent/algorithms/environment.py:105-112`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L105-L112)).
- **BR-FIN-02 (Field Ownership Boundary)**: Customers can only authorize operations on fields registered under their own `customer_id` ([`mcp_server/tools.py:144-150`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L144-L150)).

---

## 4. Health, Safety & Emergency Rules
- **BR-SAFE-01 (Allergy Tank Decontamination)**: Spray tanks used for organophosphate chemicals must undergo verified chemical decontamination before dispatching to customers with documented allergies ([`agent/algorithms/environment.py:114-121`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L114-L121)).
- **BR-SAFE-02 (Emergency Spill Response)**: In the event of a chemical leak or valve fault, the operator must trigger an emergency stop, isolate the area, and log an incident note ([`rag/docs/equipment_manuals.txt:18`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/docs/equipment_manuals.txt#L18), [`mcp_server/server.py:75-77`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L75-L77)).
