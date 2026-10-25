# AnyIO 4.15.1 Dependency Study & Architecture Reference

## Executive Summary

`anyio` is an asynchronous compatibility and structured-concurrency library providing a unified, high-level API over `asyncio` and `trio`. In **Sherlock-V2**, AnyIO is installed as version **4.15.1** in `.venv\Lib\site-packages\anyio`. It enters the project dependency graph transitively via `httpx` (version 0.28.1) and its HTTP transport engine `httpcore` (version 1.0.7), which are used by `flet` (1.0.4), `phonsint` (0.1.0), and `user-scanner` (1.5.2.3).

This reference documents AnyIO's internal architecture, key concurrency primitives (task groups, cancel scopes, memory streams, semaphores/capacity limiters), integration points with HTTPX/Flet, and its strategic value in redesigning the background scan worker thread and cancellation mechanism in Sherlock-V2.

---

## 1. Version & Package Information

- **Package Name**: `anyio`
- **Installed Version**: `4.15.1`
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/anyio`
- **Metadata Citation**: `anyio-4.15.1.dist-info\METADATA:1-30`
- **Supported Python Runtimes**: `>=3.10` up to `3.15` (explicitly tested on Python 3.14 free-threading, see `METADATA:21-23`).
- **Module Structure**:
  - `anyio\__init__.py:11-155`: Lazy import dispatcher (`_lazyimport.py:43`) exporting core primitives (`create_task_group`, `CancelScope`, `create_memory_object_stream`, `CapacityLimiter`, `Semaphore`, etc.).
  - `anyio\abc\_tasks.py`: Abstract definitions of `TaskGroup` and `TaskStatus`.
  - `anyio\_core\_tasks.py`: Frontend factory functions and `CancelScope` / `TaskHandle` abstractions.
  - `anyio\_core\_synchronization.py`: `Semaphore`, `CapacityLimiter`, `Event`, and `Lock`.
  - `anyio\_core\_streams.py` & `anyio\streams\memory.py`: Bounded/unbounded object streams.
  - `anyio\_backends\_asyncio.py`: Asyncio implementation of the backend (`AsyncIOBackend`), task groups, cancel scopes, and synchronization wrappers.
  - `anyio\from_thread.py`: Cross-thread execution bridge (`BlockingPortal`, `run`, `run_sync`, `start_blocking_portal`).
  - `anyio\to_thread.py`: Worker-thread dispatching for blocking operations (`run_sync`).

---

## 2. Task Groups (Structured Concurrency)

AnyIO enforces structured concurrency: tasks spawned inside a task group are bounded by that group's lifecycle. A task group cannot exit until all spawned child tasks have finished or been cancelled.

### 2.1 Abstract Interface & API Contract
- **File**: `anyio\abc\_tasks.py:89-224`
- **Lifecycle Context**: `async with create_task_group() as tg:` enters via `__aenter__` (`:213`) and waits for all child tasks on `__aexit__` (`:217`).
- **Spawning Methods**:
  - `tg.start_soon(func, *args, name=...)` (`anyio\abc\_tasks.py:138-158`): Non-blocking schedule. Returns a `TaskHandle` (`_core\_tasks.py:250-465`) that allows checking status (`PENDING`, `FINISHED`, `CANCELLING`, `CANCELLED`, `FAILED`), retrieving return values, or individual task cancellation.
  - `await tg.start(func, *args, name=..., return_handle=False)` (`anyio\abc\_tasks.py:161-210`): Starts a task and suspends until the child calls `task_status.started(value)`. Enables deterministic initialization order (e.g., worker ready, socket bound).
  - `tg.cancel(reason=None)` (`anyio\abc\_tasks.py:105-117`): Convenience shortcut to immediately trigger `tg.cancel_scope.cancel(reason)`.

### 2.2 AsyncIO Backend Implementation
- **File**: `anyio\_backends\_asyncio.py:783-1035`
- **Scope Hierarchy**: In `TaskGroup.__init__`, a root `CancelScope` is instantiated (`:785`). Entering `__aenter__` activates this cancel scope (`:797`).
- **Task Spawning (`_spawn`)**:
  - Tasks are wrapped in `TaskHandle._run_coro()` (`:932`) and scheduled on the loop via `loop.create_task` or eager task factories (`:934-944`).
  - State tracking: Tasks are registered in `_task_states[task]` (`:955`) and attached to `initial_scope._tasks` (`:956`).
  - Python 3.14+ integration: `asyncio.future_add_to_awaited_by(task, self.cancel_scope._host_task)` (`:958-959`) for native task graph visualization and crash reporting.
- **Completion & Teardown (`__aexit__`)**:
  - Lines `800-860`: If an unhandled exception occurs in the body or in any child task, `self.cancel_scope.cancel()` is called immediately (`:808`).
  - Remaining tasks are drained under a shielded wait scope (`:815-837`).
  - Multiple exceptions are collected into `self._exceptions` and raised as a `BaseExceptionGroup("unhandled errors in a TaskGroup", self._exceptions)` (`:847-849`).

---

## 3. Cancel Scopes

Cancel scopes decouple cancellation from task lifetime, allowing any arbitrary block of asynchronous code to be timed out, cancelled, or shielded without spawning separate tasks.

### 3.1 Frontend Functions
- **File**: `anyio\_core\_tasks.py`
  - `CancelScope(*, deadline=math.inf, shield=False)` (`:43-125`)
  - `fail_after(delay, shield=False, reason=None)` (`:158-181`): Context manager raising `TimeoutError` on expiry.
  - `fail_at(deadline, shield=False, reason=None)` (`:127-157`): Context manager with absolute deadline.
  - `move_on_after(delay, shield=False)` (`:201-220`): Context manager that suppresses timeout cancellation without raising.
  - `move_on_at(deadline, shield=False)` (`:182-200`): Suppressed timeout at absolute timestamp.
  - `current_effective_deadline()` (`:222-236`): Returns nearest active deadline in scope stack.

### 3.2 Internals & Cancellation Mechanics on AsyncIO
- **File**: `anyio\_backends\_asyncio.py:384-720`
- **Scope Tree**:
  - Scopes form a parent-child tree (`_parent_scope`, `_child_scopes`, lines `:407-408`).
  - When entered (`__enter__`, `:422-452`), the active scope for `_host_task` is swapped and nested.
- **Cancellation Delivery (`_deliver_cancellation`)**:
  - Lines `:581-629`: Recursively iterates over all tasks in `self._tasks` and child scopes in `self._child_scopes`.
  - For each eligible task, calls `task.cancel(origin._cancel_reason)` (`:607`).
  - If tasks are still active, schedules another delivery cycle via `loop.call_soon(self._deliver_cancellation, origin)` (`:623-625`).
- **Suppression vs Re-raising (`__exit__`)**:
  - Lines `:497-536`: When `self._cancel_called` is true, AnyIO checks whether the cancellation was initiated by this scope or an outer scope (`_parent_cancellation_is_visible_to_us`, `:566-571`).
  - If initiated by this scope, it sets `self._cancelled_caught = True` and swallows the cancellation exception (`:534`), returning `True` from `__exit__`.
  - Level-cancellation (Python 3.11+): Calls `self._host_task.uncancel()` (`:500`) for each unconsumed cancellation level.
- **Shielding (`shield=True`)**:
  - Lines `:558-560`, `:616-618`, `:710-720`: A shielded scope isolates its inner tasks and child scopes from external cancellation delivery while still allowing internal timeouts and cancellation.

---

## 4. Streams (Memory & IO)

AnyIO provides stream abstractions for type-safe, asynchronous streaming with backpressure.

### 4.1 Memory Object Streams
- **Constructor**: `create_memory_object_stream[T_Item](max_buffer_size=0)` (`anyio\_core\_streams.py:16-53`)
- **State & Channel Tracking**: `anyio\streams\memory.py:55-77` (`_MemoryObjectStreamState`).
  - Holds `buffer: deque[T_Item]`, `open_send_channels: int`, `open_receive_channels: int`.
  - Tracks waiting senders/receivers with `OrderedDict[Event, ...]`.
- **Receive Stream (`MemoryObjectReceiveStream`)**: `anyio\streams\memory.py:79-196`
  - `await stream.receive()` (`:115-134`): Waits until an item is pushed or throws `EndOfStream` (`:133`) when all senders close.
  - `stream.receive_nowait()` (`:87-113`): Synchronous non-blocking pull; raises `WouldBlock` (`:113`) or `EndOfStream`.
  - `stream.clone()` (`:135-149`): Increments `open_receive_channels` for multi-consumer setups.
  - `stream.close()` / `await stream.aclose()` (`:150-168`): Decrements channel count. When 0, wakes blocked senders with `BrokenResourceError`.
- **Send Stream (`MemoryObjectSendStream`)**: `anyio\streams\memory.py:198-327`
  - `await stream.send(item)` (`:235-264`): Pushes item into buffer. If `len(buffer) >= max_buffer_size`, suspends until a receiver consumes.
  - `stream.send_nowait(item)` (`:206-234`): Raises `WouldBlock` if buffer is full; raises `BrokenResourceError` (`:221`) if all receivers closed.
  - `stream.clone()` (`:265-279`): Clones send channel for multi-producer pipelines.
  - `stream.close()` (`:280-296`): Decrements `open_send_channels`. When 0, unblocks receivers with `EndOfStream`.

### 4.2 Byte & Network Streams
- `anyio\streams\buffered.py`: `BufferedByteReceiveStream` for buffered byte stream decoding.
- `anyio\streams\tls.py`: `TLSStream.wrap` for TLS encryption handshakes over raw byte streams.
- `anyio\streams\file.py`: `FileReadStream` and `FileWriteStream` for non-blocking file IO.

---

## 5. Synchronization Primitives: Semaphores vs Capacity Limiters

AnyIO provides two distinct primitives in `anyio\_core\_synchronization.py` to regulate concurrent access.

| Feature | `Semaphore` (`:388-472`) | `CapacityLimiter` (`:534-650`) |
| :--- | :--- | :--- |
| **Model** | Counter / Permit model (`initial_value`, `max_value`) | Token borrowing tied to borrower identity |
| **Borrower Validation** | No tracking. Any task can call `release()`. | Tracks borrower (defaults to current `TaskInfo`). Releasing by non-borrower raises `RuntimeError`. |
| **Double Acquire** | Allowed (can acquire multiple times if counter > 0). | Prohibited for the same borrower; prevents recursive deadlocks. |
| **Delegated Borrowing** | None. | `acquire_on_behalf_of(borrower)` and `release_on_behalf_of(borrower)`. |
| **Dynamic Resizing** | Fixed at instantiation. | `limiter.total_tokens` is writable at runtime (`:571-574`). Increasing immediately wakes waiting tasks. |
| **Fast Acquire Option** | Supported (`fast_acquire=True`, `:396`). | No. |
| **Use in Sherlock-V2** | Local resource gating (e.g. max 5 simultaneous disk writes). | **Global scan concurrency control** (e.g. 50 simultaneous site checks, dynamically adjustable). |

---

## 6. HTTPX and Flet Integration

### 6.1 How HTTPX & HTTPCore Use AnyIO
HTTPX does not implement socket connections directly; it delegates async transport to `httpcore` (version 1.0.7 in `.venv\Lib\site-packages\httpcore`). `httpcore` specifically uses AnyIO as its asyncio network backend.

1. **Network Backend (`httpcore\_backends\anyio.py`)**:
   - `AnyIOBackend.connect_tcp`: Lines `:98-123` call `await anyio.connect_tcp(remote_host, remote_port, local_host)`. Socket connection is wrapped in `with anyio.fail_after(timeout):` (`:114`).
   - `AnyIOBackend.connect_unix_socket`: Lines `:125-144` call `await anyio.connect_unix(path)` guarded by `anyio.fail_after`.
   - `AnyIOStream`: Lines `:21-95` wrap `anyio.abc.ByteStream`. `read()` (`:25-37`) and `write()` (`:39-51`) run under `with anyio.fail_after(timeout):` and translate AnyIO exceptions (`BrokenResourceError`, `EndOfStream`) into HTTPCore exceptions (`ReadError`, `WriteError`).
   - `start_tls`: Lines `:55-80` call `await anyio.streams.tls.TLSStream.wrap(self._stream, ssl_context, ...)` inside `anyio.fail_after(timeout)`.
2. **Synchronization Primitives (`httpcore\_synchronization.py`)**:
   - `httpcore` detects the event loop via `sniffio.current_async_library()` (`:22-45`).
   - `AsyncLock`: Uses `anyio.Lock()` (`:68`).
   - `AsyncEvent`: Uses `anyio.Event()` with `anyio.fail_after` (`:126, 150`).
   - `AsyncSemaphore`: Uses `anyio.Semaphore(bound, max_value=bound)` (`:170`).
   - `AsyncShieldCancellation`: Uses `anyio.CancelScope(shield=True)` (`:208, 214, 226`) to shield socket closing during connection teardown.

### 6.2 How Flet Interacts with AsyncIO & AnyIO
- **Flet Main Loop (`flet\app.py:133-147`)**:
  - `flet.app.run()` launches the application using `asyncio.run(run_async(...))` on the main thread.
  - The entire Flet UI event dispatching and WebSocket/socket server runs on this primary `asyncio` event loop.
- **HTTPX inside Flet**:
  - Flet uses HTTPX for authentication workflows (`flet\auth\authorization_service.py`, `flet\auth\providers\github_oauth_provider.py`).
- **Threading Boundary**:
  - Long-running CPU-bound or network-flooding tasks (like username enumeration across 5,000+ sites) cannot run directly on Flet's UI event loop without causing frame drops and unresponsive controls.
  - They must run in a background worker thread, requiring reliable cross-thread signaling and cancellation.

---

## 7. Relevance to Sherlock-V2 Scan Worker Thread & Cancellation Design

### 7.1 Existing Sherlock v1 Design & Limitations
In Sherlock v1 (`Sherlock\src\services\sherlock_service.py`), scanning runs in a background thread:
- **Loop Creation**: `_run_maigret_worker_thread` (`sherlock_service.py:685-696`) manually creates `worker_loop = asyncio.new_event_loop()`, sets it as current, and runs `worker_loop.run_until_complete(_runner())`.
- **Cancellation Handle**: A custom `_CancelHandle` (`sherlock_service.py:540-559`) stores references to `loop` and `task`.
- **Cross-Thread Cancel**: When the user clicks Cancel in the UI, `SherlockService.cancel()` (`sherlock_service.py:1360`) invokes `loop.call_soon_threadsafe(task.cancel)` (`:552`).
- **Teardown Fragility**:
  - In `finally` (`sherlock_service.py:962-970`), pending tasks are collected via `asyncio.all_tasks(worker_loop)`, cancelled individually in a loop, and gathered with `return_exceptions=True`.
  - If third-party libraries spawn sub-tasks or don't observe cancellation promptly, in-flight TCP sockets linger until their default timeouts expire (~30-60 seconds), consuming bandwidth and battery.
  - The UI thread must poll or wait on a `threading.Event`.

### 7.2 Sherlock-V2 AnyIO Architectural Blueprint

AnyIO solves each of these pain points directly through structured concurrency and thread-bridging primitives.

```
       +-------------------------------------------------------------+
       |                   Flet Main UI Thread                       |
       |  (Runs standard asyncio loop via flet.app.run / run_async)  |
       +------------------------------+------------------------------+
                                      |
                     User clicks [Cancel Scan] button
                                      |
         portal.call(cancel_scope.cancel, "User cancelled scan")
                                      |
  ====================================v===================================== (Thread Boundary)
                                      |
       +-------------------------------------------------------------+
       |               Background Scan Worker Thread                 |
       |            (Managed by start_blocking_portal)               |
       |                                                             |
       |  +-------------------------------------------------------+  |
       |  | CancelScope (scan_scope)                              |  |
       |  |                                                       |  |
       |  |  +-------------------------------------------------+  |  |
       |  |  | TaskGroup (tg)                                  |  |  |
       |  |  |                                                 |  |  |
       |  |  |  CapacityLimiter(total_tokens=50)               |  |  |
       |  |  |                                                 |  |  |
       |  |  |  +----------------+  +----------------+         |  |  |
       |  |  |  | Check Site A   |  | Check Site B   |  ...    |  |  |
       |  |  |  | (httpcore/tcp) |  | (httpcore/tcp) |         |  |  |
       |  |  |  +-------+--------+  +-------+--------+         |  |  |
       |  |  +----------|-------------------|------------------+  |  |
       |  +-------------|-------------------|---------------------+  |
       +----------------|-------------------|------------------------+
                        |                   |
                        v                   v
      emit result ticks via send_stream.send(progress)
                        |
                        v
        MemoryObjectReceiveStream (consumed by UI Flusher)
```

#### Key Architecture Principles:

1. **Zero Orphan Tasks via `TaskGroup`**:
   - By structuring all 5,000+ site checks within an `anyio.create_task_group()`, no task can escape the group's lifetime.
   - When the scan scope is cancelled, `tg.cancel_scope.cancel()` immediately delivers cancellation down the entire task tree (`anyio\_backends\_asyncio.py:581-629`).
2. **Immediate Socket Abort via HTTPCore / AnyIO Integration**:
   - Because HTTPX's transport (`httpcore`) uses `anyio.fail_after` and `AnyIOStream.read/write` (`httpcore\_backends\anyio.py:25-51`), cancelling the cancel scope triggers immediate socket closure at the OS level.
   - This prevents the "invisible drain" where background HTTP connections keep reading response bodies for minutes after cancellation.
3. **Clean Cross-Thread Management via `BlockingPortal`**:
   - `anyio.from_thread.start_blocking_portal(backend="asyncio")` (`anyio\from_thread.py:506-568`) provides a production-grade context manager that manages the worker thread, its event loop, and task lifecycle.
   - The UI thread can dispatch a scan via `future = portal.start_task_soon(run_scan)`.
   - Cancelling the scan is as simple as `future.cancel()` or `portal.call(scan_scope.cancel)`. AnyIO handles thread synchronization without manual `loop.call_soon_threadsafe` or tracking dead loops.
4. **Dynamic Concurrency Throttling via `CapacityLimiter`**:
   - Replace manual semaphore logic with `anyio.CapacityLimiter(max_conns)` (`anyio\_core\_synchronization.py:534`).
   - If the scanner encounters HTTP 429 rate-limiting or switches to mobile data, `limiter.total_tokens` can be dialed down dynamically at runtime (e.g. from 50 to 10) without restarting the scan.
5. **Decoupled Progress Streaming via Memory Object Stream**:
   - Replace direct UI callbacks (`on_progress_cb`) with `send_stream, receive_stream = create_memory_object_stream[SearchProgress](max_buffer_size=200)`.
   - The worker pushes results into `send_stream`. If Flet UI rendering slows down, the stream buffer provides bounded backpressure, preventing memory spikes.
   - When the scan completes or cancels, closing `send_stream` cleanly triggers `EndOfStream` in the UI consumer task.

---

## 8. Verified Code Citation Index

| Component | File Path | Line Range | Key Symbols & Roles |
| :--- | :--- | :--- | :--- |
| **Package Metadata** | `anyio-4.15.1.dist-info\METADATA` | `1-30` | Version 4.15.1, dependencies (`idna`, `typing_extensions`), Python 3.14 support. |
| **Public API Exports** | `anyio\__init__.py` | `11-155` | Lazy imports, public symbols export, deprecation aliases. |
| **TaskGroup ABC** | `anyio\abc\_tasks.py` | `89-224` | `TaskGroup` protocol, `start_soon`, `start`, `cancel`, `__aenter__`, `__aexit__`. |
| **TaskGroup AsyncIO** | `anyio\_backends\_asyncio.py` | `783-1035` | Concrete asyncio `TaskGroup`, `_spawn`, exception gathering into `BaseExceptionGroup`. |
| **TaskHandle** | `anyio\_core\_tasks.py` | `250-465` | `TaskHandle`, status enum, `wait()`, `cancel()`, `return_value`. |
| **CancelScope Frontend** | `anyio\_core\_tasks.py` | `43-125` | `CancelScope` class facade, `deadline`, `shield`, `cancel()`. |
| **Timeout Helpers** | `anyio\_core\_tasks.py` | `127-220` | `fail_at`, `fail_after`, `move_on_at`, `move_on_after`. |
| **CancelScope AsyncIO** | `anyio\_backends\_asyncio.py` | `384-720` | Cancellation tree delivery (`:581`), level uncancelling (`:500`), exception swallowing (`:534`). |
| **Memory Stream API** | `anyio\_core\_streams.py` | `16-53` | `create_memory_object_stream[T]` generic factory. |
| **Memory Stream Impl** | `anyio\streams\memory.py` | `79-327` | `MemoryObjectReceiveStream`, `MemoryObjectSendStream`, cloning, `EndOfStream`. |
| **Synchronization** | `anyio\_core\_synchronization.py` | `388-650` | `Semaphore` (`:388-472`), `CapacityLimiter` (`:534-650`). |
| **Thread Bridge** | `anyio\from_thread.py` | `187-447`, `506-568` | `BlockingPortal`, `start_blocking_portal`, `run`, `run_sync`. |
| **HTTPCore Network** | `httpcore\_backends\anyio.py` | `21-147` | `AnyIOStream`, `AnyIOBackend`, `connect_tcp`, `start_tls`, `fail_after`. |
| **HTTPCore Sync** | `httpcore\_synchronization.py` | `48-228` | `AsyncLock`, `AsyncEvent`, `AsyncSemaphore`, `AsyncShieldCancellation`. |
| **Flet Entry Point** | `flet\app.py` | `68-147` | `run()`, `run_async()`, `asyncio.run()` event loop invocation. |
| **Sherlock v1 Legacy** | `Sherlock\src\services\sherlock_service.py` | `540-559`, `656-977` | Manual worker loop, `_CancelHandle`, `call_soon_threadsafe`, teardown loop. |
