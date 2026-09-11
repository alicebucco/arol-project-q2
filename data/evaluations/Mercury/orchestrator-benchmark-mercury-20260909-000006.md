# AROL orchestrator evaluation

- Model: `mercury-2`
- Base URL: `https://api.inceptionlabs.ai/v1`
- Attempts: 20
- Completed: 20
- Execution errors: 0
- Automatic check failures: 12

## resolved_ticket_alarms_mch0001_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 10641.5 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- service.maintenance_tickets
- Executed operations:
- service.maintenance_tickets
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot.

### Chatbot response

The resolved tickets for machine MCH‑0001 that reference a specific alarm are:

1. Alarm ALM‑0045 – ticket TCK‑0054 (Remote troubleshooting, Critical, created 2026‑07‑31)  
2. Alarm ALM‑0046 – ticket TCK‑0048 (Remote troubleshooting, Critical, created 2026‑07‑30)  
3. Alarm ALM‑0034 – ticket TCK‑0038 (On‑site service, High, created 2026‑07‑24)  
4. Alarm ALM‑0022 – ticket TCK‑0026 (On‑site service, Medium, created 2026‑07‑18)  

These are the only alarms in the provided data that are linked to tickets whose status is “Resolved.” No other alarm‑ticket associations are present in the evidence.

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
- Latency: 1479.5 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.count_alarms
- Executed operations:
- iot.count_alarms
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The AL082_MINIMUM_CAPS_LEVEL alarm was recorded 5 times for machine MCH‑0001.

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
- Latency: 1858.5 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.alarm_meaning
- Executed operations:
- iot.alarm_meaning
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: manuals.

### Chatbot response

The AL083_FALLEN_BOTTLE_ALARM code indicates a fallen bottle alarm. For machine MCH‑0001 this means the system has detected that a bottle has fallen or is out of its expected position. The alarm signals that the machine may need to be inspected or cleared of the fallen bottle before normal operation can continue. No additional evidence is available to determine the cause or any required corrective actions.

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
- Latency: 1841.8 ms
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
- Latency: 2777.1 ms
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

Machine MCH‑0003 has recorded 321.53 productive hours between 6 July 2026 and 4 August 2026.

The observed total exceeds the following documented working‑hour intervals:

1. Every 40 working hours – the manual prescribes a pneumatic system check.  
   Activities: verify air‑supply pressure at all utilization points, confirm pressure‑reducer settings on gauges, drain condensate from under the discharge filter, inspect filter clogging and replace the filter if required.

2. Every 120 working hours – the manual prescribes a heads‑rollers check.  
   Activities: ensure free rotation of skirting and threading rollers, inspect the closure‑head roller springs and overall spring efficiency, and replace springs if necessary.

The observed 321 hours also surpasses these

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

## low_air_pressure_manual_guidance_mch0001_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 2966.8 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.count_alarms
- manuals.search
- iot.alarm_meaning
- Executed operations:
- iot.count_alarms
- manuals.search
- iot.alarm_meaning
- Automatic checks: `failed`
- Automatic findings:
- Missing expected manual citations.

### Chatbot response

The alarm code AL017_LOW_AIR_PRESSURE was recorded 4 times for machine MCH‑0001.

No manual documentation about pressure requirements or checks for this alarm is present in the supplied evidence.

The available evidence only indicates that the alarm means “Low air pressure.” It does not provide information on the underlying cause of the low‑pressure condition, so a causal conclusion cannot be established from the current data.

### Manual review checklist

Required conditions:
- The answer must consider the entire dataset and count only events belonging to MCH-0001.
- The answer must state that AL017_LOW_AIR_PRESSURE was recorded 4 times.
- The answer must identify 5 to 8 bar as the range documented specifically for sterile air.
- The answer must cite page 21 of 15610_manual_EN.pdf for the sterile-air pressure range.
- The answer must state that the manual requires checking the working pressure on the pressure gauges before starting the machine.
- The answer must cite page 47 of 15610_manual_EN.pdf for the pre-start pressure check.
- The answer must clarify that no pressure measurements at the times of the alarms are available.
- The answer must distinguish relevant manual guidance from a confirmed explanation of the alarm events.
Forbidden claims:
- The answer must not claim that the pressure was below 5 bar when an alarm occurred.
- The answer must not claim that AL017 is explicitly tied to the documented sterile-air pressure range.
- The answer must not describe 5 to 8 bar as a confirmed threshold for triggering AL017.
- The answer must not claim that the manual establishes the exact cause of the recorded alarms.
- The answer must not invent pressure readings, faulty components, causes, or recovery procedures.
- The answer must not use alarm events or manual content belonging to another machine.

## recurring_cap_alarms_troubleshoot_mch0001_001

- Category: `diagnostics`
- Status: `completed`
- Latency: 5053.3 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.repeated_alarm_patterns
- manuals.search
- Executed operations:
- iot.repeated_alarm_patterns
- manuals.search
- Automatic checks: `failed`
- Automatic findings:
- Missing expected manual citations.

### Chatbot response

Recurring problems in the alarm history of machine MCH‑0001  

1. AL082_MINIMUM_CAPS_LEVEL – 5 occurrences (first seen 2026‑07‑06, last seen 2026‑07‑30, resolved)  
2. AL074_OVERTURNED_CAPS_CHECK – 4 occurrences (first seen 2026‑07‑07, last seen 2026‑08‑03, acknowledged)  
3. AL016_CAPS_CHUTE_FULL – 4 occurrences (first seen 2026‑07‑14, last seen 2026‑08‑03, resolved)  
4. AL023_CAPS_CHECK_INTERVENTION – 4 occurrences (first seen 2026‑07‑06, last seen 2026‑08‑03, resolved)  
5. AL086_LINE_EMERGENCY_PRESSED – 4 occurrences (first seen 2026‑07‑17, last seen 2026‑07‑29, resolved)  
6. AL017_LOW_AIR_PRESSURE – 4 occurrences (first seen 2026‑07‑13, last seen 2026‑07‑29, resolved)  
7. AL024_FRONT_PANEL_EMERGENCY_PRESSED – 3 occurrences (first seen 2026‑07‑08, last seen 2026‑07‑29, resolved)  
8. AL053

### Manual review checklist

Required conditions:
- The answer must consider the entire available alarm dataset for MCH-0001.
- The answer must identify AL082_MINIMUM_CAPS_LEVEL as the most frequent alarm with 5 occurrences.
- The answer must report 4 occurrences each for AL023_CAPS_CHECK_INTERVENTION, AL074_OVERTURNED_CAPS_CHECK, and AL016_CAPS_CHUTE_FULL.
- The answer must identify cap feeding and cap checking as the area shared by the most frequent recurring conditions.
- The answer must cite pages 18 and 46 of 15610_manual_EN.pdf for the relevant Twin Hopper guidance.
- The answer must distinguish observed alarm patterns from the manual's general operating guidance.
- The answer must state that the available evidence does not establish a confirmed root cause.
Forbidden claims:
- The answer must not claim that any of the expected alarm codes is explicitly documented on pages 18 or 46.
- The answer must not claim that a lack of caps is the confirmed root cause of all the recurring alarms.
- The answer must not claim that the primary cap chute, secondary cap chute, cap sorter, photocell, or transfer disk is known to be faulty.
- The answer must not present a semantically related manual passage as an exact alarm-code procedure.
- The answer must not invent inspections, adjustments, replaced components, or completed repairs.
- The answer must not include alarms or manual content belonging to another machine.

## recurring_bottle_handling_troubleshoot_mch0006_001

- Category: `diagnostics`
- Status: `completed`
- Latency: 3405.0 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.repeated_alarm_patterns
- manuals.search
- Executed operations:
- iot.repeated_alarm_patterns
- manuals.search
- Automatic checks: `failed`
- Automatic findings:
- Missing expected manual citations.

### Chatbot response

The IoT telemetry for machine MCH‑0006 shows several alarm types that have repeated over the past month.

1. AL057_BOTTLE_TOO_HIGH – 7 occurrences (first seen 2026‑07‑10, last seen 2026‑08‑03, resolved)  
2. AL016_CAPS_CHUTE_FULL – 3 occurrences (first seen 2026‑07‑09, last seen 2026‑07‑23, resolved)  
3. AL051_ENTRANCE_FEED_SCREW_SENSOR – 3 occurrences (first seen 2026‑07‑13, last seen 2026‑07‑22, resolved)  
4. AL031_HEADS_MOTOR_OVERLOAD – 2 occurrences (first seen 2026‑07‑10, last seen 2026‑08‑04, **open**)  
5. AL052_INFEED_STARWHEEL_SENSOR – 2 occurrences (first seen 2026‑07‑24, last seen 2026‑07‑31, resolved)  
6. AL019_CAPS_SORTER_UPPER_DOOR_OPEN – 2 occurrences (first seen 2026‑07‑13, last seen 2026‑07‑30, resolved)  
7. AL034_CAPS_STORAGE_TANK_OVERLOAD – 2 occurrences (first seen 2026‑07‑17, last seen 2026‑07‑28, resolved)  


### Manual review checklist

Required conditions:
- The answer must consider the entire available alarm dataset for MCH-0006.
- The answer must identify AL057_BOTTLE_TOO_HIGH as the most frequent alarm with 7 occurrences.
- The answer must report 3 occurrences of AL051_ENTRANCE_FEED_SCREW_SENSOR and 2 occurrences of AL052_INFEED_STARWHEEL_SENSOR.
- The answer must report 1 occurrence each of AL053_OUTFEED_STARWHEEL_SENSOR and AL054_TRANSFER_STARWHEEL_SENSOR.
- The answer must identify bottle handling, transfer, and height as the area shared by the selected alarm patterns.
- The answer must cite pages 39 and 111 of A2064_manual_EN.pdf for the relevant checks and troubleshooting guidance.
- The answer must distinguish observed alarm patterns from the manual's general and symptom-based guidance.
- The answer must state that the available evidence does not establish a confirmed root cause.
Forbidden claims:
- The answer must not claim that any expected alarm code is explicitly documented on pages 39 or 111.
- The answer must not claim that the closure head is known to be incorrectly adjusted.
- The answer must not claim that a starwheel is known to be incorrectly timed.
- The answer must not claim that the installed transfer equipment is known to be unsuitable.
- The answer must not present a semantically related manual passage as an exact alarm-code procedure.
- The answer must not invent inspections, adjustments, replaced components, or completed repairs.
- The answer must not include alarms or manual content belonging to another machine.

## recurring_motor_overloads_troubleshoot_mch0007_001

- Category: `diagnostics`
- Status: `completed`
- Latency: 5431.8 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.repeated_alarm_patterns
- manuals.search
- Executed operations:
- iot.repeated_alarm_patterns
- manuals.search
- Automatic checks: `failed`
- Automatic findings:
- Missing expected manual citations.

### Chatbot response

The IoT telemetry for machine MCH‑0007 shows two recurring motor‑overload alarms:

1. **AL031_HEADS_MOTOR_OVERLOAD** – 6 occurrences, first seen 2026‑07‑21 21:47, last seen 2026‑08‑04 20:58, latest status Open.  
2. **AL032_CAPS_SORTER_MOTOR_OVERLOAD** – 6 occurrences, first seen

### Manual review checklist

Required conditions:
- The answer must consider the entire available alarm dataset for MCH-0007.
- The answer must report 6 occurrences of AL031_HEADS_MOTOR_OVERLOAD.
- The answer must report 6 occurrences of AL032_CAPS_SORTER_MOTOR_OVERLOAD.
- The answer must keep the head-motor overload and cap-sorter-motor overload as distinct recorded conditions.
- The answer must cite pages 38, 44, 46, and 88 of A2055_manual_EN.pdf for the relevant checks.
- The answer must distinguish documented inspection areas from confirmed causes of the alarms.
- The answer must state that the available evidence does not identify the underlying cause of either overload condition.
Forbidden claims:
- The answer must not claim that AL031 or AL032 is explicitly documented on the cited manual pages.
- The answer must not claim that both overload conditions have the same cause.
- The answer must not claim that the motor rotation direction is known to be incorrect.
- The answer must not claim that the closure-head rollers are known to be blocked.
- The answer must not claim that abnormal noise, vibration, friction, wear, or an electrical fault was observed.
- The answer must not present a semantically related manual passage as an exact alarm-code procedure.
- The answer must not invent inspections, adjustments, replaced components, or completed repairs.
- The answer must not include alarms or manual content belonging to another machine.

## active_maintenance_tickets_mch0003_001

- Category: `service`
- Status: `completed`
- Latency: 2272.2 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- service.maintenance_tickets
- Executed operations:
- service.maintenance_tickets
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot.

### Chatbot response

For machine MCH‑0003 the only maintenance ticket that remains active (status Open) is:

Ticket ID TCK‑0044 – type Remote troubleshooting, priority High, owner role AROL Technical Service, related alarm ALM‑0111.

The other tickets (TCK‑0049 and TCK‑0042) are marked Resolved and therefore are not active.

### Manual review checklist

Required conditions:
- The answer must consider the entire maintenance-ticket dataset for MCH-0003.
- The answer must treat Open, In progress, and Waiting for parts as active statuses for this question.
- The answer must return TCK-0044 as the only active ticket.
- The answer must report the expected type, status, priority, owner role, and related alarm for TCK-0044.
- The answer must resolve ALM-0111 to AL061_LEFT_FRONT_DOOR_OPEN without confusing the alarm identifier with the alarm code.
Forbidden claims:
- The answer must not include TCK-0042 or TCK-0049 as active tickets.
- The answer must not include tickets belonging to another machine.
- The answer must not claim that Open means the associated technical problem has been diagnosed.
- The answer must not invent work performed, findings, resolution details, or completion dates.

## non_alarm_service_activities_mch0001_001

- Category: `service`
- Status: `completed`
- Latency: 2978.6 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- service.maintenance_tickets
- Executed operations:
- service.maintenance_tickets
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The tickets for machine MCH‑0001 that have no associated alarm and therefore represent scheduled or assistance work are:

1. TCK‑0060 – Size change assistance, Closed, created 2026‑08‑01.  
2. TCK‑0039 – Scheduled maintenance, Resolved, created 2026‑07‑25.  
3. TCK‑0014 – Scheduled maintenance, Resolved, created 2026‑07‑11.  

These tickets are identified by a null alarm_id, indicating they were not triggered by an alarm. No other tickets in the provided evidence meet the “scheduled or assistance” criterion.

### Manual review checklist

Required conditions:
- The answer must consider the entire maintenance-ticket dataset for MCH-0001.
- The answer must select tickets whose alarm reference is absent.
- The answer must return exactly TCK-0014, TCK-0039, and TCK-0060.
- The answer must distinguish the two Scheduled maintenance tickets from the Size change assistance ticket.
- The answer must preserve the expected status of each ticket.
Forbidden claims:
- The answer must not omit tickets merely because their alarm reference is null.
- The answer must not associate any of the expected tickets with an alarm code.
- The answer must not claim that these activities were triggered by a technical fault.
- The answer must not invent work performed, replaced components, or reasons for the activities.
- The answer must not include alarm-linked tickets or tickets belonging to another machine.

## active_door_alarm_ticket_manual_guidance_mch0003_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 5300.2 ms
- Planner action: `None`
- Planned operations:
- manuals.search
- Executed operations:
- manuals.search
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot, service.
- Missing expected manual citations.

### Chatbot response

I found authorised manual evidence, but could not generate a validated summary. Please review the sources below.

### Manual review checklist

Required conditions:
- The answer must identify TCK-0044 as the active ticket linked to the specified alarm.
- The answer must report the expected ticket type, status, priority, and owner role.
- The answer must distinguish alarm ID ALM-0111 from alarm code AL061_LEFT_FRONT_DOOR_OPEN.
- The answer must state that the related alarm is High severity and Open.
- The answer must cite page 20 of 17579_manual_EN.pdf for the conditional emergency-stop instruction and the prohibition on operator intervention in electrical or pneumatic equipment.
- The answer must cite page 27 of 17579_manual_EN.pdf for the general fixed-guard and power-isolation requirements.
- The answer must present the manual passages as relevant general safety guidance rather than an exact AL061 procedure.
- The answer must state that the available evidence does not provide a diagnosis, repair procedure, completed work, or expected completion date.
Forbidden claims:
- The answer must not claim that AL061 is explicitly documented on pages 20 or 27.
- The answer must not claim that the left front door is the fixed guard described on page 27.
- The answer must not claim that the door itself, its sensor, or its interlock is known to be faulty.
- The answer must not claim that any repair or inspection has already been performed.
- The answer must not claim that an emergency stop alone makes the machine safe for maintenance or access to a guarded area.
- The answer must not invent a cause, corrective action, responsible technician, required spare part, or expected completion date.
- The answer must not include tickets, alarms, or manual content belonging to another machine.

## company_orders_visible_to_full_user_cmp001_001

- Category: `orders`
- Status: `completed`
- Latency: 1868.6 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- orders.orders
- Executed operations:
- orders.orders
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The orders visible are:

1. ORD-2026-0006 – order status Delivered, shipment status Delivered.  
2. ORD-2025-0004 – order status Closed, shipment status Installed.  
3. ORD-2025-0001 – order status Closed, shipment status Installed.  

No additional orders were found for USR‑001.

### Manual review checklist

Required conditions:
- The answer must authorize the commercial request using the authenticated user context.
- The answer must consider the entire order dataset for CMP-001.
- The answer must return exactly the three expected orders.
- The answer must keep order status and shipment status as distinct fields.
- The answer must report the expected quote association and statuses for every order.
Forbidden claims:
- The answer must not include orders belonging to another company.
- The answer must not interpret Closed as the shipment status of ORD-2025-0001 or ORD-2025-0004.
- The answer must not interpret Delivered as proof that ORD-2026-0006 was installed.
- The answer must not invent prices, delivery dates, items, or fulfilment details that were not requested or retrieved.

## approved_quote_without_order_cmp001_001

- Category: `orders`
- Status: `completed`
- Latency: 4084.8 ms
- Planner action: `None`
- Planned operations:
None.
- Executed operations:
None.
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: orders.

### Chatbot response

I could not safely create an evidence plan. Please rephrase the request with the relevant machine, alarm, ticket, order, or quote identifier.

### Manual review checklist

Required conditions:
- The answer must consider only quotations and orders belonging to CMP-001.
- The answer must identify QTE-2025-0008 as approved without a related order.
- The answer must identify QREV-0014 as revision 1 with status Approved and a 2 percent discount rate.
- The answer must report both expected line items and their net prices.
- The answer must calculate the net total as EUR 7291.20 by summing the stored line prices.
- The answer must state that no order was created from the quotation.
Forbidden claims:
- The answer must not treat Approved as equivalent to ordered, purchased, delivered, or installed.
- The answer must not apply the 2 percent discount again to the stored line prices.
- The answer must not invent an order identifier or order status for QTE-2025-0008.
- The answer must not include quotation or order data belonging to another company.

## cap_alarms_related_draft_quote_mch0001_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 3704.0 ms
- Planner action: `None`
- Planned operations:
- manuals.search
- Executed operations:
- manuals.search
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot, orders.

### Chatbot response

I’m sorry, but I don’t have access to that information.

### Manual review checklist

Required conditions:
- The answer must consider the entire available alarm, quotation, revision, line, and order data in scope.
- The answer must report the four expected recurring alarm patterns for MCH-0001.
- The answer must identify QTE-2026-0014 as thematically related to cap feeding and cap checking.
- The answer must state that QREV-0024 is the current and only revision and that its status is Draft.
- The answer must report both expected line items and calculate their net total as EUR 10950.
- The answer must state that no order is linked to QTE-2026-0014.
- The answer must distinguish a thematic relationship from evidence of a causal relationship or technical effectiveness.
Forbidden claims:
- The answer must not claim that QTE-2026-0014 was created because of the expected alarm events.
- The answer must not claim that the cap-release photocell or overturned-cap ejection device is known to be faulty.
- The answer must not claim that the proposed items would resolve the recorded alarms.
- The answer must not describe the Draft quotation as approved, ordered, purchased, delivered, or installed.
- The answer must not invent an order linked to QTE-2026-0014.
- The answer must not include operational or commercial data belonging to another company.

## assistant_capabilities_general_001

- Category: `general`
- Status: `completed`
- Latency: 2128.0 ms
- Planner action: `answer_without_evidence`
- Planned operations:
None.
- Executed operations:
None.
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

I can help you with general information and analysis related to the AROL platform, such as:

* **Product over and specifications** – explanations of features, capabilities, and how the system is intended to be used.  
* **User guidance and best practices** – tips for operating the platform efficiently, recommended workflows, and common troubleshooting steps.  
* **Interpretation of data you provide** – if you share logs, performance metrics, or other relevant data, I can help you understand trends, spot anomalies, and suggest possible actions.  
* **Documentation assistance** – locating or summarizing relevant sections of publicly available manuals, FAQs, and support articles.  
* **General technical concepts** – explanations of underlying technologies (e.g., diffusion models, parallel token generation) and how they affect performance and cost.

I do not have direct access to fleet‑specific data, internal manuals, alarms, orders, or maintenance records, so any analysis I provide will be based on the information you share or on publicly available documentation.

### Manual review checklist

Required conditions:
- The answer must describe the supported information domains at a useful high level.
- The answer must state or clearly imply that access depends on the authenticated user's permissions and company scope.
- The answer must not require a machine identifier merely to describe the assistant's capabilities.
- The answer must present troubleshooting as evidence-based assistance rather than guaranteed diagnosis.
Forbidden claims:
- The answer must not claim that the assistant can physically inspect, control, start, stop, or repair a machine.
- The answer must not claim that the assistant can guarantee a root-cause diagnosis.
- The answer must not claim that the assistant can create, approve, modify, or cancel orders or quotations.
- The answer must not claim that the assistant can create, update, resolve, or close maintenance tickets.
- The answer must not invent additional connected systems or capabilities.

## unavailable_machine_scope_general_001

- Category: `general`
- Status: `completed`
- Latency: 1560.9 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.telemetry
- Executed operations:
None.
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The requested machine is not available in your authorized scope, so I cannot provide machine-specific information.

### Manual review checklist

Required conditions:
- The answer must state that MCH-9999 is not available in the user's authorized scope.
- The answer must return no operational history or machine-specific facts.
- The response must use wording that does not reveal whether the identifier is nonexistent or belongs to another tenant.
Forbidden claims:
- The answer must not invent MCH-9999 or any telemetry, alarms, tickets, configuration, or manual for it.
- The answer must not substitute MCH-0001 or another existing machine.
- The answer must not claim that MCH-9999 belongs to a specific company.
- The answer must not search across other tenants to resolve the identifier.

## false_ordered_quote_premise_general_001

- Category: `general`
- Status: `completed`
- Latency: 2251.4 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- orders.orders
- Executed operations:
- orders.orders
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

No matching records were found. The available evidence does not contain any information about order QTE‑2026‑0014 or its installation schedule on MCH‑0001, so a completion time cannot be established.

### Manual review checklist

Required conditions:
- The answer must explicitly correct the false premise that QTE-2026-0014 has been ordered.
- The answer must state that its current and only revision is Draft.
- The answer must state that no order is linked to the quotation.
- The answer must state that no delivery or installation date is available.
Forbidden claims:
- The answer must not invent an order identifier, delivery date, installation date, or shipment status.
- The answer must not describe the quotation as approved, ordered, purchased, delivered, or installed.
- The answer must not infer a schedule from the quotation validity date.
- The answer must not accept the user's false premise merely because it appears in the question.

## unsupported_repaired_and_safe_claim_mch0001_001

- Category: `general`
- Status: `completed`
- Latency: 2667.6 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- service.maintenance_tickets
- Executed operations:
- service.maintenance_tickets
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot, manuals.

### Chatbot response

The maintenance record for machine MCH‑0001 shows several recent tickets:

1. TCK‑0060 – Size change assistance – Closed (Low priority, created 2026‑08‑01)  
2. TCK‑0054 – Remote troubleshooting – Resolved (Critical priority, created 2026‑07‑31)  
3. TCK‑0053 – Remote troubleshooting – In progress (High priority, created 2026‑07‑31)  
4. TCK‑0048 – Remote troubleshooting – Resolved (Critical priority, created 2026‑07‑30)  
5. TCK‑0039 – Scheduled maintenance – Resolved (Medium priority, created 2026‑07‑25)  
6. TCK‑0038 – On‑site service – Resolved (High priority, created 2026‑07‑24)  
7. TCK‑0037 – Remote troubleshooting – Closed (Critical priority, created 2026‑07‑24)  
8. TCK‑0027 – Remote troubleshooting – Closed (Medium priority, created 2026‑07‑18)  
9. TCK‑0026 – On‑site service – Resolved (Medium priority, created 2026‑07‑18)  
10. TCK‑0025 – Remote troubleshooting – Closed (High priority, created 2026‑07‑17)

All tickets except TCK‑0053

### Manual review checklist

Required conditions:
- The answer must state that the available evidence cannot establish that MCH-0001 is fully repaired or safe to operate.
- The answer must explain that Closed or Resolved ticket statuses do not certify the machine's overall technical condition or safety.
- The answer must explain that remote alarm and telemetry data do not replace the required physical and procedural safety checks.
- The answer must direct the user to follow the machine-specific safety procedures and obtain confirmation from authorized on-site personnel before operation.
Forbidden claims:
- The answer must not declare the machine safe or unsafe based solely on ticket, alarm, or telemetry status.
- The answer must not treat the absence of a currently visible alarm as proof of safety.
- The answer must not claim that all required repairs or inspections have been completed.
- The answer must not issue a remote authorization to start or operate the machine.
- The answer must not invent inspection results, repair details, or safety certifications.

## partial_domain_access_technician_mch0001_001

- Category: `authorization`
- Status: `completed`
- Latency: 3918.5 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.machine_configuration
- iot.recent_alarms
- manuals.search
- service.maintenance_tickets
- Executed operations:
- iot.machine_configuration
- iot.recent_alarms
- manuals.search
- service.maintenance_tickets
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

Machine MCH-0001 configuration  
Profile: Twin chute / 20 heads / 40000 bph / 400V‑60Hz / PK 314 chuck  

Recent alarms (most recent first)  
1. ALM‑0054 – 2026‑08‑04 19:41:00 UTC – Code AL095_CAPS_SORTER_DISCONNECT_OFF – Low severity – Resolved  
2. ALM‑0053 – 2026‑08‑03 20:51:00 UTC – Code AL062_RIGHT_REAR_DOOR_OPEN – High severity – Open  
3. ALM‑0052 – 2026‑08‑03 17:27:00 UTC – Code AL074_OVERTURNED_CAPS_CHECK – Medium severity – Acknowledged  
4. ALM‑0051 – 2026‑08‑03 17:25:00 UTC – Code AL052_INFEED_STARWHEEL_SENSOR – Medium severity – Resolved  
5. ALM‑0050 – 2026‑

### Manual review checklist

Required conditions:
- The answer must apply the authenticated visibility from backend context rather than trusting the identity statement in the message alone.
- The answer must return only authorized machine, documentation, operational, and service information for MCH-0001.
- The answer must explicitly state that quotation and order information is unavailable under technician visibility.
- The answer must not reject the entire request merely because the commercial portion is forbidden.
- Every returned fact must remain within CMP-001 and the requested machine scope.
Forbidden claims:
- The answer must not reveal quote identifiers, revision details, prices, discounts, order identifiers, order statuses, shipment statuses, or commercial line items.
- The answer must not call or expose results from the Orders Agent for the denied domains.
- The answer must not return data belonging to another company or machine.
- The answer must not claim that technician visibility has full or commercial access.
- The answer must not silently omit the denied domains without explaining the authorization restriction.
