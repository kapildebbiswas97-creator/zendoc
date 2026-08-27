# ZENDOC Central Intelligence

Milestone 2 adds a central AI orchestration foundation. It does not claim clinical validation and does not replace clinicians.

## Flow

User message
-> deterministic safety layer
-> intent router
-> minimal user/conversation context
-> specialized local guidance or provider abstraction
-> structured response
-> AI audit metadata

## Key Modules

- `zendoc.safety`: deterministic emergency red-flag detection.
- `zendoc.intent`: intent router for health, appointments, records, medicine, fitness, nutrition, monitoring, and general assistant intents.
- `zendoc.ai_provider`: provider abstraction with safe local fallback.
- `zendoc.intelligence`: central orchestrator.
- `zendoc.ai_types`: structured response schema.
- `zendoc.healthcare_finder`: Milestone 3 finder handoff for provider/facility discovery.

## Safety Rules

Emergency detection is deterministic and runs before provider or assistant logic. If emergency indicators are found, the normal chat flow stops and the response contains `emergency: true`.

Healthcare-related intents now return `find_healthcare` actions with category/specialty metadata. Actual search results must come from the provider network or configured places provider.

## Privacy

The orchestration layer uses minimum necessary user context. It does not dump all medical records into prompts. Conversations are scoped by `user_id`.

## API

`POST /api/v1/ai/message`

Request:

```json
{
  "message": "I have fever",
  "conversation_id": 1
}
```

Response:

```json
{
  "intent": "symptoms",
  "urgency": "routine",
  "message": "Human-readable guidance",
  "follow_up_questions": [],
  "possible_actions": [],
  "specialist": null,
  "emergency": false,
  "provider": "local_fallback",
  "success": true,
  "conversation_id": "1",
  "next_step": "Recommended action"
}
```
