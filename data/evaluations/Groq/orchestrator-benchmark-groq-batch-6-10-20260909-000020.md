# AROL orchestrator evaluation

- Model: `openai/gpt-oss-20b`
- Base URL: `https://api.groq.com/openai/v1`
- Attempts: 5
- Completed: 5
- Execution errors: 0
- Automatic check failures: 4

## low_air_pressure_manual_guidance_mch0001_001

- Category: `multi_agent`
- Status: `completed`
- Latency: 9005.3 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- iot.count_alarms
- manuals.search
- Executed operations:
- iot.count_alarms
- manuals.search
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The dataset shows that the alarm code AL017_LOW_AIR_PRESSURE was recorded four times for machine MCH‑0001.  

No manual, service, or order evidence was retrieved that describes pressure requirements or checks for this machine.  

Because the only evidence available is the alarm count, the data cannot establish why the alarms occurred.

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
- Latency: 32072.8 ms
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

Recurring problems in the alarm history of

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
- Latency: 37438.4 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- manuals.search
- iot.repeated_alarm_patterns
- Executed operations:
- manuals.search
- iot.repeated_alarm_patterns
- Automatic checks: `failed`
- Automatic findings:
- Missing expected manual citations.

### Chatbot response

Recurring bottle‑handling alarms for machine MCH‑0006

1. AL057_BOTTLE_TOO_HIGH – 7 occurrences from 2026‑07‑10 to 2026‑08‑03, all resolved.  
2. AL016_CAPS_CHUTE_FULL – 3 occurrences from 2026‑07‑09 to 2026‑07‑23, all resolved.  
3. AL051_ENTRANCE_FEED_SCREW_SENSOR – 3 occurrences from 2026‑07‑13 to 2026‑07‑22, all resolved.  
4. AL031_HEADS_MOTOR_OVERLOAD – 2 occurrences from 2026‑07‑10 to 2026‑08‑04, status Open.  
5. AL052_INFEED_STARWHEEL_SENSOR – 2 occurrences from 2026‑

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
- Latency: 43044.6 ms
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

Recurring motor‑overload conditions for MCH‑0007

1. AL031_HEADS_MOTOR_OVERLOAD – 6 occurrences, first seen 2026‑07‑21, last seen 2026‑08‑04, status Open.  
2. AL032_CAPS_SORTER_MOTOR_OVERLOAD – 6 occurrences, first seen 2026‑07‑08, last seen 2026‑07‑31, status Resolved.

Relevant manual checks

No manual guidance evidence was retrieved for MCH‑0007 in the current dataset. Therefore, specific checks that would apply to the heads motor or caps sorter motor cannot be cited from the available sources.

Underlying cause

The available

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
- Latency: 37597.6 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- service.maintenance_tickets
- Executed operations:
- service.maintenance_tickets
- Automatic checks: `failed`
- Automatic findings:
- Missing expected agents: iot.

### Chatbot response

Active maintenance tickets for machine MCH‑0003 (as of 2026‑08‑05):

1. Ticket ID TCK‑0044  
   • Type: Remote troubleshooting  
   • Priority: High  
   • Owner role: AROL Technical Service  
   • Related alarm: ALM‑0111  

No other tickets for MCH‑0003 are currently active.

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
