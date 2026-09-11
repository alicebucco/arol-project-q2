# AROL orchestrator evaluation

- Model: `openai/gpt-oss-20b`
- Base URL: `https://api.groq.com/openai/v1`
- Attempts: 5
- Completed: 5
- Execution errors: 0
- Automatic check failures: 3

## resolved_ticket_alarms_mch0001_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 11846.6 ms
- Planner action: `None`
- Planned operations:
- manuals.search
- Executed operations:
- manuals.search
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot, service.

### Chatbot response

I’m sorry, but I don’t have access to that information.

### Manual review checklist

Required conditions:
- The answer must consider the entire dataset.
- The answer must consider only alarms belonging to MCH-0001.
- Every returned alarm must be linked to a ticket whose status is Resolved.
- The answer must return exactly the four expected alarm codes.
- The answer must report one resolved ticket for each expected alarm code.
Forbidden claims:
- The answer must not include alarms linked only to open or unresolved tickets.
- The answer must not include data belonging to other machines.
- The answer must not confuse the number of resolved tickets with the total number of alarm events.

## alarm_occurrence_count_mch0001_001

- Category: `alarm_analysis`
- Status: `completed`
- Latency: 24490.6 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.count_alarms
- Executed operations:
- iot.count_alarms
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The alarm code AL082_MINIMUM_CAPS_LEVEL was recorded 5 times for machine MCH‑0001.

### Manual review checklist

Required conditions:
- The answer must consider the entire dataset.
- The answer must count only events belonging to MCH-0001.
- The answer must state that AL082_MINIMUM_CAPS_LEVEL was recorded 5 times.
Forbidden claims:
- The answer must not count alarms belonging to other machines.
- The answer must not interpret 5 as the number of tickets.
- The answer must not add causes or procedures that were not requested.

## undocumented_alarm_guidance_mch0001_001

- Category: `alarm_guidance`
- Status: `completed`
- Latency: 32861.6 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.alarm_meaning
- Executed operations:
- iot.alarm_meaning
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: manuals.

### Chatbot response

The alarm code **AL083_FALLEN_BOTTLE_ALARM** on machine **MCH‑0001** is identified as a “Fallen bottle alarm”. This indicates that the system has detected a bottle that has fallen or is no longer in its expected position.  

No additional evidence is available to explain why the bottle fell, what corrective action is required, or whether the machine is safe to operate. Therefore, the meaning of the code is limited to the detection of a fallen bottle; it does not provide a causal conclusion or repair guidance.

### Manual review checklist

Required conditions:
- The answer must explain that the readable code name refers to a fallen bottle alarm.
- The answer must clarify that this meaning is inferred from the code name.
- The answer must state that AL083 was not found explicitly in the available manual.
- The answer must state that specific causes or procedures cannot be confirmed.
Forbidden claims:
- The answer must not claim that AL083 is explicitly documented in the manual.
- The answer must not invent the cause of the fallen bottle.
- The answer must not invent checks or recovery procedures.
- The answer must not present semantically similar passages as confirmed documentation for AL083.

## maintenance_man_qualities_mch0001_001

- Category: `manuals`
- Status: `completed`
- Latency: 23058.6 ms
- Planner action: `answer_without_evidence`
- Planned operations:
- manuals.search
- Executed operations:
- manuals.search
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

I found authorised manual evidence, but could not generate a validated summary. Please review the sources below.

### Manual review checklist

Required conditions:
- The answer must be based on the manual associated with MCH-0001.
- The answer must include a citation to page 24 of 15610_manual_EN.pdf.
- The answer must preserve the meaning of the documented requirements without adding unsupported qualifications.
Forbidden claims:
- The answer must not invent certifications, degrees, licences, or training requirements not stated in the source passage.
- The answer must not use operational, alarm, service, or commercial data.
- The answer must not cite a different manual as the supporting source.

## observed_hours_maintenance_mch0003_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 48289.3 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.observed_productive_hours
- manuals.maintenance_requirements
- Executed operations:
- iot.observed_productive_hours
- manuals.maintenance_requirements
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: service.
- Missing expected manual citations.

### Chatbot response

Productive hours observed for machine MCH‑0003: 321.53 hours (from 2026‑07‑06 to 2026‑08‑04).  
The manual specifies maintenance intervals in working hours. The thresholds that are lower than or equal to the observed hours are:

1. **Every 40 working hours** – “Pneumatic system check. Check the air supply pressure to the various utilization points. Check by the gauges that the pressure reducers are adjusted at the work pressure. Drain the possible condensate collected under the discharge filter. Check the filter clogging. If necessary, replace it.”

2. **Every 120 working hours** – “Heads rollers check. Check the perfect rotation of the skirting and threading rollers (they must turn freely). Check the closure head rollers springs. Check the efficiency of the springs in general and replace them if necessary.”

The 1000‑, 6000‑, and 12000‑hour intervals are not reached with the current telemetry window.

No evidence of service calls or orders relating to MCH‑0003 was found in the retrieved data.  
The manual guidance does not prove that the maintenance has actually been performed; it only documents what is recommended at those intervals.

### Manual review checklist

Required conditions:
- The answer must describe 321.53 hours as productive hours observed in the available telemetry window.
- The answer must state that the 40-hour maintenance interval has been reached repeatedly.
- The answer must identify 320 hours as the latest reached 40-hour interval.
- The answer must identify 500 hours as the next documented threshold.
- The answer must mention checking the operation of the safety devices.
- The answer must mention checking the pneumatic system.
- The answer must cite page 97 of 17579_manual_EN.pdf for the documented 40-hour activities.
- The answer must clarify that the available data does not show whether these maintenance activities have already been completed.
Forbidden claims:
- The answer must not describe 321.53 hours as the machine's lifetime operating hours.
- The answer must not claim with certainty that maintenance is overdue.
- The answer must not claim that the 500-hour threshold has been reached.
- The answer must not invent additional maintenance activities.
- The answer must not claim that the maintenance completion history is available.
