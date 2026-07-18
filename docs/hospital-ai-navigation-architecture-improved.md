# Hospital AI Navigation Architecture — Improved Agent Flow

## 1. Design principles

- Emergency detection runs before normal agent processing.
- The system does not require an intent router before the agent.
- The LLM agent selects tools using native tool calling.
- The backend controls which tools are visible based on authorization and workflow state.
- Every tool call passes through an allowlist, schema validation, and policy checks.
- Read operations may execute automatically; write operations require confirmation or staff approval.
- Tool observations return to the agent, allowing a bounded ReAct loop.
- Factual responses must be grounded in approved evidence and include valid citations.
- If the system lacks sufficient evidence or exhausts its execution budget, it abstains or hands off to hospital staff.

## 2. Simplified bounded agent flow

```mermaid
flowchart TD
    input["Chat Request"]
    prepare["Minimal Validation + Vietnamese Normalization<br/>preserve original text"]
    emergency["Emergency Detection<br/>rules + Vietnamese classifier"]
    emergency_result{"Emergency risk?"}
    sop["Hospital-approved Emergency SOP<br/>no diagnosis or treatment advice"]
    agent["Bounded Tool-Calling Agent<br/>model selects next tool or final answer"]
    policy["Tool Policy Gate<br/>allowlist + schema + auth + workflow state"]
    allowed{"Tool call allowed?"}
    approval{"Confirmation required?"}
    confirm["Pause and Request Confirmation"]
    tool["Execute Tool"]
    observation["Validated Observation<br/>result + source + freshness"]
    budget{"Task complete and within budget?"}
    verify["Grounding + Citation Verification"]
    valid{"Response valid?"}
    response["Return Cited Response"]
    fallback["Safe Abstention or Human Handoff"]

    input --> prepare
    prepare --> emergency
    emergency --> emergency_result

    emergency_result -->|High or uncertain| sop
    sop --> response

    emergency_result -->|Low| agent
    agent -->|Tool call| policy
    agent -->|Final answer| verify
    agent -->|Cannot proceed| fallback

    policy --> allowed
    allowed -->|No| fallback
    allowed -->|Yes| approval

    approval -->|No| tool
    approval -->|Yes| confirm
    confirm -->|Approved| tool
    confirm -->|Rejected or edited| agent

    tool --> observation
    observation --> budget
    budget -->|Continue| agent
    budget -->|Complete| verify
    budget -->|Limit exceeded| fallback

    verify --> valid
    valid -->|Yes| response
    valid -->|No| fallback
    fallback --> response
```

## 3. Security boundary

Security is applied throughout the system instead of being represented as a single blocking step before emergency detection.

```mermaid
flowchart LR
    user["Patient or Caregiver"]
    validation["Input Validation<br/>rate limit + format + size"]
    emergency["Emergency Gate"]

    subgraph controlled["Controlled Agent Boundary"]
        agent["Tool-Calling Agent"]
        policy["Tool Policy"]
        tools["Allowlisted Tools"]
        verify["Output Verification"]

        agent --> policy
        policy --> tools
        tools -->|Observation| agent
        agent --> verify
    end

    user --> validation
    validation --> emergency
    emergency -->|Emergency| sop["Approved Emergency SOP"]
    emergency -->|Normal| agent
    sop --> result["User-visible Response"]
    verify --> result
```

Security controls include:

- Before the agent: request-size limits, Unicode validation, rate limiting, and lightweight Vietnamese normalization.
- During model calls: prompt separation, minimized patient data, and no credentials or secrets in model context.
- Before tool execution: tool allowlist, argument-schema validation, authentication, authorization, workflow-state checks, and approval gates.
- After execution: PII filtering, source and freshness validation, grounding checks, and citation completeness.

Emergency handling takes priority even if a message also resembles a prompt-injection attempt.

## 4. Tool availability model

The system does not select tool groups by intent. The agent determines which tool is useful, while the backend limits tool visibility using user permissions and workflow state.

```mermaid
flowchart TD
    state["User Identity + Consent + Workflow State"]
    provider["Dynamic Tool Provider"]
    public["Public Read Tools"]
    authenticated["Authenticated Read Tools"]
    draft["Draft Tools"]
    write["Approval-required Request Tools"]
    staff["Staff-only Tools<br/>never exposed to patient agent"]
    visible["Allowed Tool Subset"]
    agent["LLM Agent Selects Tool"]

    state --> provider
    public --> provider
    authenticated --> provider
    draft --> provider
    write --> provider
    staff -.->|excluded| provider
    provider --> visible
    visible --> agent
```

The effective tool set is:

```text
Visible tools
    = tools allowed for the current workflow state
    ∩ tools authorized for the current user
    ∩ tools allowed by system policy
```

### Public read tools

```text
search_official_knowledge
get_locations
get_departments
get_doctors
get_services
get_working_hours
get_service_prices
get_available_slots
```

### Authenticated patient tools

```text
get_patient_appointments
get_appointment_request_status
```

### Draft tools

```text
create_appointment_draft
```

### Approval-required request tools

```text
submit_appointment_request
request_reschedule
request_cancellation
```

### Staff-only operations

The patient-facing agent must never receive these tools:

```text
confirm_appointment
reject_appointment
update_medical_record
change_service_price
```

## 5. Booking workflow with human approval

```mermaid
stateDiagram-v2
    [*] --> Exploring

    Exploring --> DraftReady: Agent finds slot and collects required information
    DraftReady --> AwaitingPatientConfirmation: Create appointment draft
    AwaitingPatientConfirmation --> DraftReady: Patient requests changes
    AwaitingPatientConfirmation --> PendingStaffReview: Patient confirms submission

    PendingStaffReview --> Confirmed: Hospital staff approves
    PendingStaffReview --> Rejected: Hospital staff rejects
    PendingStaffReview --> NeedsInformation: More information required

    NeedsInformation --> DraftReady
    Confirmed --> [*]
    Rejected --> [*]
```

The following states are distinct:

```text
Appointment draft
    != Appointment request
    != Confirmed appointment
```

The agent may create a draft. It may submit a request only after patient confirmation. The official appointment is confirmed only by authorized hospital staff.

## 6. Bounded execution controls

Each agent run should have explicit limits:

```json
{
  "max_tool_calls": 6,
  "max_repairs": 1,
  "deadline_ms": 12000,
  "tool_calls_used": 0,
  "visited_calls": []
}
```

Required runtime rules:

- Do not repeat the same tool with identical arguments unless the underlying state changed.
- Do not allow the model to unlock additional write permissions.
- Reject tools that are absent from the current allowlist.
- Stop when the tool-call budget or deadline is exhausted.
- Require an idempotency key for every write operation.
- Validate every dynamic result for source, retrieval time, and freshness.
- Audit tool name, validated arguments, authorization outcome, result status, and approval decision.
- Never store hidden chain-of-thought; store tool calls, observations, state transitions, and final decisions instead.

## 7. Grounded response validation

```mermaid
flowchart TD
    compose["Compose Response<br/>claims + source references"]
    support{"Every factual claim supported?"}
    citation{"Every factual claim has a valid citation?"}
    freshness{"Dynamic facts sufficiently fresh?"}
    answer["Return Cited Answer"]
    repair["Remove or Repair Unsupported Claims Once"]
    fallback["Abstain or Human Handoff"]

    compose --> support
    support -->|Yes| citation
    support -->|No| repair
    citation -->|Yes| freshness
    citation -->|No| repair
    freshness -->|Yes| answer
    freshness -->|No| fallback
    repair --> support
    repair -.->|repair budget exhausted| fallback
```

Static hospital information must come from approved, versioned knowledge. Dynamic information such as schedules, slots, appointment states, and current prices should come from authoritative hospital APIs whenever available.

## 8. Orchestration technology and provider defaults

- LangGraph is the orchestration runtime for graph state, conditional routing, durable execution, streaming, and human-in-the-loop interrupts.
- The graph does not contain an intent-router node. The model selects the next tool through native tool calling from the backend-provided visible tool subset.
- Emergency detection, authorization, tool policy, schema validation, confirmation, grounding, and audit remain application-controlled graph nodes.
- PostgreSQL-backed LangGraph checkpoints are used outside tests; in-memory checkpoints are test-only.
- OpenAI is the default LLM provider. Provider and model are runtime settings, not capability/API contracts.

```text
LLM_PROVIDER=openai
LLM_MODEL=gpt-5-mini
OPENAI_API_KEY=<server-side secret>
```

Changing `LLM_PROVIDER` or `LLM_MODEL` must not change tool schemas, graph state contracts, safety behavior, or capability response envelopes. Unsupported providers/models fail configuration validation at startup. Provider failure follows the configured fallback policy; no provider failure may bypass the local emergency path or grounding requirements.
