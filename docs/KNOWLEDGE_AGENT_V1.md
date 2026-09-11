# Knowledge Agent v1

The Knowledge Agent is a read-only evidence coordinator. It is deliberately narrower than a medical chatbot.

## Execution order

`authenticated actor`
→ `deterministic emergency screen`
→ `approved medical-knowledge retrieval`
→ `provenance-bound evidence bundle`
→ `no healthcare action`

If the emergency screen triggers, retrieval is skipped and the response directs the user toward emergency care. The agent does not continue chatting through a red-flag pathway.

If no approved indexed evidence matches, the agent returns `NO_APPROVED_EVIDENCE`. It does not answer from model memory while pretending retrieval succeeded.

If evidence exists, the agent returns `EVIDENCE_READY`, bounded excerpts and exact source/document/version/hash provenance. `answer` remains `null` in v1.

## Action authority

The Knowledge Agent cannot:

- diagnose;
- prescribe;
- modify a prescription;
- book an appointment;
- place an order;
- dispatch emergency services;
- mutate Health Memory;
- bypass consent or authorization;
- execute SQL, shell commands or arbitrary tools.

A later explanation model may consume this evidence only after a separate grounding/output-safety evaluation gate.

## API

`POST /api/v1/health-knowledge/agent`

Example request body:

```json
{
  "query": "What does blood pressure monitoring mean?",
  "limit": 6
}
```

The endpoint requires normal ZENDOC API authentication.
