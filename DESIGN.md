# PickMeBeforeTheyDo — System Design

## 1. Project Overview

PickMeBeforeTheyDo is a delivery-task and order-management platform.

V1 implements the core delivery-task workflow:

- Store Managers create and manage delivery tasks.
- Delivery Persons see the highest-priority available task.
- Delivery Persons can accept, decline, and complete tasks.
- Store Managers receive real-time notifications about relevant task state changes.
- The system maintains consistency for task assignment and the maximum pending-task constraint.

V1 is intentionally a **modular monolith**. Distributed infrastructure is introduced where it solves a specific problem.

## 2. Core Actors

### Store Manager

Can:

- Create delivery tasks.
- View tasks they created.
- View task history.
- Cancel tasks that are still `NEW`.
- Receive notifications when a task is accepted, declined, or cancelled.

### Delivery Person

Can:

- View the highest-priority available task.
- Accept a task.
- Decline an accepted task assigned to them.
- Complete an accepted task.
- View previously accepted tasks.

A Delivery Person can have at most **3 pending tasks**.

A pending task is an `ACCEPTED` task that has not yet been completed or declined.

## 3. Core Domain Model

### User / Employee

Django's authentication user model represents application users.

A role determines whether the user is:

- `STORE_MANAGER`
- `DELIVERY_PERSON`

The initial implementation use Django's user model with a role extension/profile rather than a separate authentication system.

### DeliveryPerson

A one-to-one relationship with the Delivery Person user.

It maintains delivery-person-specific information, including:

```text
pending_task_count
```

This is the number of tasks currently in `ACCEPTED` state and assigned to that Delivery Person.

### Task

```text
id
title
priority
created_by
created_at
current_state
assigned_to
```

The database is authoritative for the current task state.

### TaskStateTransition

```text
task
from_state
to_state
action
actor
timestamp
```

Every successful state transition is recorded.

### OutboxEvent

```text
event_id
event_type
aggregate_id
payload
created_at
published_at
```

An OutboxEvent is created in the same database transaction as the state change that produced it.

## 4. Task State Machine

Valid transitions:

```text
NEW ───────────────► ACCEPTED ─────────► COMPLETED
 │                       │
 │                       │
 │                       └──────────────► NEW
 │                              decline
 │
 └────────────────────────────► CANCELLED
```

More explicitly:

```text
NEW → ACCEPTED       (Delivery Person accepts)
NEW → CANCELLED      (Store Manager cancels)
ACCEPTED → COMPLETED (Delivery Person completes)
ACCEPTED → NEW       (Delivery Person declines)
```

State changes should go through domain/application operations such as:

```text
accept()
decline()
complete()
cancel()
```

Application code should not arbitrarily mutate `current_state`.

## 5. Task Ordering

Available tasks are tasks whose state is `NEW`.

PostgreSQL remains the source of truth for the available task set.

Ordering:

```text
priority DESC
created_at ASC
id ASC
```

Therefore:

1. Higher priority wins.
2. Older tasks win when priority is equal.
3. `id` provides deterministic tie-breaking when timestamps are equal.

The system does **not** maintain an independent authoritative task queue in RabbitMQ, Redis, or application memory.

## 6. Source of Truth and Messaging

### PostgreSQL

PostgreSQL is the source of truth for:

- Users
- Tasks
- Task state
- Task assignments
- Task state-transition history
- Delivery-person pending-task count
- Outbox events

### RabbitMQ

RabbitMQ is used for asynchronous event delivery.

It is **not** the source of truth for task state and does not own the available-task queue.

Example events:

```text
TaskCreated
TaskAccepted
TaskDeclined
TaskCompleted
TaskCancelled
```

The database records the state change first; an outbox event is then published asynchronously.

## 7. Transactional Outbox

A task state change and its corresponding outbox event are committed atomically:

```text
BEGIN TRANSACTION

Update Task
Create TaskStateTransition
Update pending_task_count
Create OutboxEvent

COMMIT
```

A background publisher subsequently publishes the OutboxEvent to RabbitMQ.

This prevents:

```text
Database update succeeds
        ↓
RabbitMQ publish fails
        ↓
State changed but event was lost
```

The outbox record remains available for retry.

The outbox provides reliable eventual publication without attempting to make PostgreSQL and RabbitMQ one distributed transaction.

## 8. Idempotency

Messaging systems can deliver the same event more than once.

Every OutboxEvent therefore has a unique:

```text
event_id
```

Consumers use this identifier as the idempotency key.

Conceptually:

```text
Receive Event
     │
     ▼
Already processed?
   ┌─┴─────────┐
  Yes          No
   │            │
 Ignore       Process
                │
                ▼
        Record event_id
```

For V1, notification processing uses the event ID for idempotency.

## 9. Concurrency and Task Acceptance

The system must guarantee:

- Only one Delivery Person successfully accepts a given task.
- A Delivery Person cannot exceed 3 pending tasks.
- Task state and assignment remain consistent.
- `pending_task_count` remains consistent.

### V1: Pessimistic Locking

V1 uses PostgreSQL row-level locking through Django's:

```python
select_for_update()
```

When both rows are required, locks are acquired in this order:

```text
1. DeliveryPerson
2. Task
```

Acceptance is conceptually:

```text
BEGIN

Lock DeliveryPerson
Check pending_task_count < 3
Lock Task
Verify Task is NEW

Task → ACCEPTED
Task.assigned_to → DeliveryPerson
DeliveryPerson.pending_task_count += 1

Create TaskStateTransition
Create OutboxEvent

COMMIT
```

A concurrent attempt to accept the same task waits for the Task lock and then observes that the task is no longer `NEW`.

## 10. Why Maintain `pending_task_count`?

The count could be calculated as:

```text
COUNT(Task WHERE assigned_to=P AND current_state=ACCEPTED)
```

V1 deliberately maintains the denormalized:

```text
pending_task_count
```

This makes the capacity constraint explicit and provides a real consistency problem for the system to solve.

The count is changed transactionally:

```text
NEW → ACCEPTED
    pending_task_count += 1

ACCEPTED → COMPLETED
    pending_task_count -= 1

ACCEPTED → NEW
    pending_task_count -= 1
```

The DeliveryPerson row is locked while modifying the count.

## 11. Alternative Concurrency Strategy

V1 uses pessimistic locking.

An alternative is **optimistic concurrency control** using a version field:

```text
Task
 ├── state
 └── version
```

An update can require:

```text
WHERE id = ?
AND state = NEW
AND version = ?
```

and atomically increment the version.

If no row is updated, another transaction modified the task first.

This is documented as an alternative design. V1 does not require `version` because pessimistic locking is the selected implementation.

## 12. Real-Time Updates

Delivery Persons initially retrieve their top task through:

```text
GET /api/delivery/top-task/
```

They then establish:

```text
/ws/tasks/
```

When an event could change the available top task, the server broadcasts a lightweight notification:

```json
{
  "event": "TASK_QUEUE_CHANGED"
}
```

The client then requests the current top task through REST.

This separates:

```text
WebSocket
    ↓
"Something changed"

REST + PostgreSQL
    ↓
"What is true now?"
```

The WebSocket message is therefore not authoritative task state.

## 13. Redis and Django Channels

Django Channels provides WebSocket support.

Redis is used as the channel layer/broadcast infrastructure.

```text
Django
   │
   ▼
Redis Channel Layer
   │
   ├── Delivery Person group
   └── Store Manager group
```

Redis does not own task state.

If Redis is unavailable, PostgreSQL still contains authoritative state and clients can resynchronize through REST.

## 14. Event and Notification Flow

Example: a Delivery Person accepts a task.

```text
Delivery Person
       │
       ▼
POST /api/delivery/tasks/{id}/accept/
       │
       ▼
Django Application Service
       │
       ▼
PostgreSQL Transaction
       ├── Task → ACCEPTED
       ├── Assign Delivery Person
       ├── pending_task_count += 1
       ├── Create TaskStateTransition
       └── Create OutboxEvent
       │
       ▼
     COMMIT
       │
       ▼
Outbox Publisher
       │
       ▼
   RabbitMQ
       │
       ▼
 Celery Worker
       │
       ▼
Redis Channel Layer
       │
       ├──► Store Manager WebSocket
       └──► Delivery Person WebSocket
```

## 15. API Design

### Store Manager

```text
POST /api/tasks/
    Create a task

GET /api/tasks/
    List tasks created by the current Store Manager

GET /api/tasks/{id}/history/
    Retrieve task state-transition history

POST /api/tasks/{id}/cancel/
    Cancel a task if it is still NEW
```

### Delivery Person

```text
GET /api/delivery/top-task/
    Get the current highest-priority NEW task
    Returns 204 if no task is available

POST /api/delivery/tasks/{id}/accept/
    Accept a task

POST /api/delivery/tasks/{id}/decline/
    Decline an ACCEPTED task assigned to the current user

POST /api/delivery/tasks/{id}/complete/
    Complete an ACCEPTED task

GET /api/delivery/tasks/
    List tasks previously accepted by the current user
```

### WebSocket

```text
/ws/tasks/
```

The WebSocket connection is authenticated and associated with the appropriate user/role group.

## 16. Authentication and UI

Authentication uses Django's session-based authentication.

The initial UI uses Django templates.

Django Admin can provision/manage users and roles rather than introducing a separate user-management application in V1.

## 17. V1 Architecture

```text
                         Browser
                    ┌────────┴────────┐
                    │                 │
                   REST           WebSocket
                    │                 │
                    └────────┬────────┘
                             ▼
                          Django
                             │
                 ┌───────────┴───────────┐
                 │                       │
          Application Layer        Django Channels
                 │                       │
                 ▼                       ▼
            PostgreSQL                Redis
          Source of Truth         Channel Layer
                 │
                 │ Outbox Event
                 ▼
          Outbox Publisher
                 │
                 ▼
              RabbitMQ
                 │
                 ▼
             Celery Worker
                 │
                 └──────────────► Redis
```

V1 is a **modular monolith**. Django contains the API, application/domain logic, persistence integration, and WebSocket integration.

## 18. Initial Engineering Principles

1. PostgreSQL is the source of truth.
2. RabbitMQ transports asynchronous events; it does not own task state.
3. Redis supports real-time communication; it does not own task state.
4. State transitions are controlled by domain/application logic.
5. Important state changes and outbox events are committed atomically.
6. Event consumers are idempotent.
7. Concurrent task assignment is protected by database locking.
8. Lock ordering is consistent: DeliveryPerson → Task.
9. The three-task limit is enforced transactionally.
10. WebSocket messages notify clients of changes; PostgreSQL remains authoritative.
11. Infrastructure is introduced to solve concrete engineering problems rather than for architectural fashion.

## 19. Future Evolution

After V1 is correct and well tested, the platform can evolve into a broader Order Management / Fulfillment system.

Potential domain objects:

```text
Customer
Restaurant
Order
OrderItem
Payment
Fulfillment
DeliveryProvider
DeliveryAssignment
```

Potential external delivery integrations:

```text
                 Fulfillment Orchestrator
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        Provider A    Provider B    Provider C
          Adapter       Adapter       Adapter
```

This allows the core order-management logic to integrate with multiple delivery providers without coupling it to provider-specific APIs.

Potential future concerns:

- Provider webhooks
- Retry and failure handling
- Rate limiting
- Caching
- Horizontal scaling
- Partitioning/sharding
- Multi-region architecture
- Observability
- Distributed tracing
- CI/CD

These concerns are deliberately outside the initial V1 implementation.
