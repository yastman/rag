# CRM/HITL Policy: Booking and Inquiry Rules

**Source ID:** `policy-hitl-008`
**Category:** Internal Policy
**Last Updated:** 2026-05-01

## Human-in-the-Loop (HITL) Policy

All CRM actions require explicit human confirmation before execution.
No automated writes to the CRM are permitted without a verified
confirmation step.

## Booking Confirmation Workflow

1. User submits a booking or inquiry request through the assistant.
2. Assistant prepares the CRM action (lead creation, appointment booking,
   or document request).
3. Assistant presents the proposed action to the user with full details.
4. User must explicitly confirm the action.
5. Upon confirmation, the action is written to the CRM once.
6. A confirmation receipt is provided to the user.

## CRM Action Types

| Action | Description | Required Fields |
|---|---|---|
| `create_lead` | Create a new lead in CRM | name, phone, interest_property_id |
| `schedule_viewing` | Schedule a property viewing | lead_id, property_id, datetime |
| `request_documents` | Request property documents | lead_id, property_id, doc_type |

## Cancellation Policy

- Property viewings can be cancelled up to 2 hours before the scheduled time.
- Lead entries can be marked as inactive but not deleted.
- Document requests cannot be cancelled once submitted.

## Pricing and Fees

- All prices are listed in EUR unless otherwise stated.
- Service fees: 3% of property value for assisted viewings.
- No hidden fees; all costs are disclosed before confirmation.

## Contact

Internal policy document. For questions, consult the CRM team lead.

Reference listing ID: policy-hitl-008
