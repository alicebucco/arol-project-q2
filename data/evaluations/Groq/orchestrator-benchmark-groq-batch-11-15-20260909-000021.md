# AROL orchestrator evaluation

- Model: `openai/gpt-oss-20b`
- Base URL: `https://api.groq.com/openai/v1`
- Attempts: 5
- Completed: 5
- Execution errors: 0
- Automatic check failures: 3

## non_alarm_service_activities_mch0001_001

- Category: `service`
- Status: `completed`
- Latency: 8257.7 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- service.maintenance_tickets
- service.maintenance_tickets
- Executed operations:
- service.maintenance_tickets
- service.maintenance_tickets
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

The tickets for machine MCH‑0001 that are scheduled or assistance activities (not triggered by an alarm) are:

1. Ticket TCK‑0039 – Scheduled maintenance, resolved.
2. Ticket TCK‑0014 – Scheduled maintenance, resolved.
3. Ticket TCK‑0060 – Size change assistance, closed.

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
- Latency: 43599.0 ms
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
- Latency: 28910.3 ms
- Planner action: `retrieve_evidence`
- Planned operations:
- orders.orders
- Executed operations:
- orders.orders
- Automatic checks: `passed`
- Automatic findings:
None.

### Chatbot response

ORD-2026-0006 – order status: Delivered, shipment status: Delivered  
ORD-2025-0004 – order status: Closed, shipment status: Installed  
ORD-2025-0001 – order status: Closed, shipment status: Installed  

These are the orders returned in the dataset and their current order and shipment statuses. The evidence does not provide additional context about why the orders have these statuses or whether any further actions are required.

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
- Latency: 46954.3 ms
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
- Latency: 30297.4 ms
- Planner action: `answer_without_evidence`
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
