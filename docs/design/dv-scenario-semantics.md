# PSS-like scenario semantics in fw-hdl-dv

Status: exploration. This builds on `verification-support-review.md` §4–§6 (portable content, host C++, system model).

## User benefit

Test writers get PSS's most useful ideas in plain SystemVerilog, with no new language and no separate tool:

- Write actions as classes.
- Compose actions in parallel, in a schedule, or as a choice.
- Let the runtime work out which producer actions must run first (inference) and when shared resources are free.
- Pass values down into actions as parameters.

The same scenario then runs in other places. The SV runtime interprets it. Where its structure is static, it can be lifted into Zuspec's activity IR and run as host C++ or in the system model with full PSS solving.

## 0. Position

**Plain SV procedural code gives us sequencing for free.** It also gives us loops, conditionals, `fork/join`, `randcase` and `randomize() with {}`.

**What it lacks is the declarative layer.** No construct can see a whole group of actions before they run. Without that we can't do:
- inference,
- choosing a legal order for a `schedule`,
- static checks before the run,
- solving constraints across actions.

**So we add container *objects*.** Actions are added to a `parallel`, `schedule` or `select` object, and the container runs them. Scenarios are then built by code rather than written as statements. Containers can see their members before they start, which enables three things:
- deciding what to infer,
- choosing an order,
- checking resource conflicts.

**My view: 80–90% is right as a feature count.**
- **What's fully covered:** sequence, parallel, select, repeat and replicate, resources, one-step buffer and stream inference, component binding, exec hooks, type extension, and parameters.
- **What's missing is the *global* part of PSS:**
  - solving the whole scenario at once,
  - constraints that flow backward from consumers to producers through flow objects,
  - multi-step state inference (planning),
  - knowing a scenario is legal before it runs.

  That part is small by feature count but makes up a large share of PSS's value for *generating* tests. §5 shows how to recover most of it without changing the authoring API, because Zuspec already has the machinery.

## 1. What we have

| Asset | What it gives us |
|---|---|
| SV `fork/join`, `join_any`, `join_none`, `disable fork` | True parallel execution and most join variants |
| SV `randcase` | Weighted select. A weight expression of 0 acts as a guard |
| SV `randomize() with {}`, nested `rand` class handles, `rand_mode()`, `pre_/post_randomize` | In-place constraints. Handles that a parent and child solve together. Parameters, by fixing a field. Solve hooks |
| SV semaphores, mailboxes, events | Building blocks for resource and flow-object pools |
| SV factory and class extension | PSS `extend` and type override |
| fw-hdl component tree, visitors, and path-reachable sockets | The PSS component tree, pool scopes, and component binding |
| Zuspec activity IR (`activity.py`) | `ActivityParallel`, `ActivitySchedule`, `ActivitySelect`, `ActivityReplicate`, `JoinSpec`, `ActivityBind`, and scheduling constraints. Every container below has an IR node to lower to |
| Zuspec `pss_lower` and the scenario dialect (`scenario.py`) | Action trees, pool-binding precedence (`pools.py`, LRM 12.3), default constraints, buffer picks (`ScBufferPick`), claims (`ScClaim`), and solve problems for a whole scope (`ScScopeProblem`) |
| `zuspec-be-sw` PSS→C, dv-solve, and `zuspec-solver` blobs | A fast solver usable from SV (DPI) and from C++. Compiled per-type constraint problems |
| `zuspec-dataclasses` notes | The same programmatic direction already sketched for Python: `action.traverse(comp, a, lambda: a.activity(...))`, and "procedural code can infer an activity by claiming a data item" |

**The key point:** we aren't inventing semantics. We're adding a programmatic way to write semantics that Zuspec already represents and lowers.

## 2. Mapping PSS constructs

Tier 0 is the plain SV runtime. Tier 1 adds a planner that sees the container tree before running it (§5.1). Tier 2 adds a global solve with dv-solve over that tree (§5.2).

| PSS construct | SV programmatic form | Tier 0 | Notes |
|---|---|---|---|
| action, exec body | `class A extends fw_action #(C)` with `task body()` | ✅ | `C` is the component type. `pre_solve`/`post_solve` map to `pre_/post_randomize` |
| atomic traversal, `do A` | `` `fw_do(A) `` or `fw_do(a)` | ✅ | Steps: create, bind component, claim resources, randomize, run `body`, release |
| `do A with {…}` | `` `fw_do_with(A, {…}) `` | ✅ *in a sequence or in a `fork` branch* | Randomizes in place. Inside a container object, see §3 |
| sequence | procedural code | ✅ | Free |
| `parallel` | `fork/join`, or `fw_parallel` | ✅ | Use the object form when lookahead or a join spec is needed |
| `join_branch`/`join_select`/`join_none`/`join_first` | `p.run_join_first(n)`, `p.run_join_branch(lbl)`, … | ✅ | `join_none` and `join_first` map onto SV directly |
| `schedule` | `fw_schedule` | ✅ (randomized start order and jitter) | Data dependencies inside the schedule order themselves (§4.2). Tier 1 picks from all legal orders |
| `select` (weights, guards) | `randcase`, or `fw_select` | ✅ | The object form adds "try another branch if this one can't be solved" and records which branch ran |
| `repeat`/`foreach`/`while` | SV loops | ✅ | |
| `replicate` | a loop that adds to a container | ✅ | Labeled `replicate` maps to a `rand A a[]` handle array (§3.2) |
| action handles plus constraints across siblings | `rand A a, b;` in the compound action, with a `constraint` | ✅ **exact** | SV's nested randomize *is* PSS's handle semantics (§3.2) |
| constraints from above on anonymous traversals in a container | parameters, policies, or solving first (§3) | ⚠️ | The main gap the user named |
| resource `lock`/`share`, pools, `instance_id` constraints | `fw_lock #(R)`, `fw_share #(R)` | ✅ | Claimed at run time, all claims of an action at once (§4.1) |
| buffer input/output and inference | `fw_input #(B)`, `fw_output #(B)` | ✅ one step, just in time | §4.2 |
| stream input/output | `fw_input #(S)`, `fw_output #(S)` | ✅ | Meet-up point. An inferred producer is forked alongside the consumer |
| state flow objects | `fw_state_pool #(S)` | ⚠️ one step; multi-step needs Tier 2 | §4.3 |
| pool `bind`, default and explicit | `fw_pool` capability on a component, plus a bind table | ✅ | Must follow the same precedence as `pools.py`. Put the rule in `fw-dv-spec` |
| component binding (`comp`) | `comp` chosen at random among compatible instances, or passed as a parameter | ✅ | |
| `extend`/override | class extension plus factory override | ✅ | |
| action parameters (PSS 3.1) | assign the value, then call `rand_mode(0)` (§3.1) | ✅ | Becomes the main way to pass values down |
| coverage on action fields | covergroups in the action | ✅ | Recording which select branch, order or inference ran is new and cheap |
| whole-scenario solve, backward constraint propagation, static legality | — | ❌ | Tier 2 (§5.2), or lift into Zuspec IR (§5.3) |

## 3. Constraints from above

### 3.1 What actually breaks

Three cases work in SV today:

1. **Sequential traversal.** In-place randomization works fine: `a = new; a.randomize() with { size < lim; }; fw_run(a);`.
2. **Parallel through `fork`.** Each branch can be `` `fw_do_with(A, {…}) ``, so randomization happens when the branch starts. This is a full parallel *with* inline constraints. What we lose is container lookahead, not constraints.
3. **Containers with lookahead.** Here the action is added at one time and solved later, after component binding, resource choice and inference have happened. An inline `with {}` can't be stored in an object, and SV can't declare a class inside a task.

So the gap is narrower than "no constraints from above". It's *no constraints from above that are applied after binding, on actions handed to a container*.

### 3.2 Five ways to pass constraints down, in order of preference

1. **Parameters (PSS 3.1).** Assign the value and fix it, so it's no longer random:
   ```systemverilog
   a = dma_xfer::create();  a.size = 64;  a.size.rand_mode(0);
   // sugar: a = dma_xfer::with_(.size(64));   or  `fw_set(a, size, 64)
   ```
   The fixed field acts as a state variable in the child's own solve, so the child's constraints are still *checked*. If the child can't satisfy them, that's a located error rather than a silent override. This is the default way to pass values down. Generate a typed `with_(...)` per action with sv-weave so users don't write the `rand_mode` calls (see memory: minimal user spec).

2. **Declared handles in the compound action solve jointly, exactly as PSS does:**
   ```systemverilog
   class xfer_pair extends fw_action #(sys_c);
     rand dma_xfer a, b;
     constraint c { a.size + b.size <= 4096; a.dst != b.dst; }
     task body(); fw_parallel::of(a, b).run(); endtask
   endclass
   ```
   - The parent's randomize solves `a` and `b` together with the parent. The runtime marks them as already solved: it still binds and claims for them but doesn't randomize them again.
   - A `rand A as[]` array with `foreach` constraints covers labeled `replicate`.
   - **Limit:** constraints that depend on binding, such as `a.comp` or `a.chan.instance_id`, are solved before binding. Tier 0 handles this by making `comp` and `instance_id` random fields that the parent solves over the *candidate* set. The runtime then waits if the chosen instance is busy.

3. **Solve first, then pass results down as parameters.** This is the general Tier 0 rule for anything that crosses a boundary. Whoever knows the constraint solves for values, and the values travel as parameters. It's how inference handles a consumer's requirements on its input (§4.2).

4. **Policy objects: stored constraints in plain SV.** This is the known "constraint policy class" pattern:
   - A class holds `rand` handles to the target plus a constraint.
   - The action keeps a `rand fw_policy policies[$]`, and its randomize pulls in whatever was attached.
   - Policies are declared at class or package scope with a macro. Values captured from the caller become constructor arguments:
   ```systemverilog
   `fw_policy(small_xfer, dma_xfer, int, lim, { item.size < lim; })
   ...
   p.add(dma_xfer::create().with_policy(small_xfer::new(lim)));
   ```
   This is the one way to get true constraints that are applied after binding, inside a container. The cost is boilerplate, a named class per policy. An sv-weave annotation could generate the policies.

5. **Subclass plus factory override.** For constraints that apply to a whole test. Standard SV, nothing new.

**Recommendation:** make parameters (1) and declared handles (2) the normal style, and document policies (4) as the escape hatch. Declared handles cover most real cases where constraints cross siblings. Parameters cover most "from above" cases, because the parent usually knows a *value*, not a relation.

## 4. The runtime scheduler

### 4.1 Resources

- **Claims:** `fw_lock #(R)` and `fw_share #(R)` are fields on the action. `instance_id` is a random field.
- **When claims are taken:** after component binding and before randomize. The runtime adds an internal `instance_id inside {free}` constraint to the action's own randomize; the *runtime* adding constraints isn't a problem. If nothing is satisfiable, the action waits for a release event and tries again.
- **All claims at once:** an action takes all of its claims together or none of them. That rules out deadlock between actions holding some claims and waiting on others.
- **One difference from PSS:** in PSS, branches of a `parallel` that conflict on locks make the scenario *illegal*. At run time they simply *serialize*. Usually that's what a test writer wants. A `strict` mode on `fw_parallel` should turn it into an error, and Tier 1 checks it before the run.

### 4.2 Buffer and stream inference: pull-based, tied to scope

When a consumer needs an input, the pool it's bound to resolves it in this order:

1. **An object is available** that satisfies the consumer's requirements. Take it.
2. **A producer is already declared in an enclosing container** (the scope knows its members' outputs). Wait for it. This is what lets `schedule` and `parallel` order data dependencies themselves.
3. **Otherwise, infer.** Choose a producer action type registered for this object type, at random and weighted. Run it just in time, with the consumer's requirements passed as parameters to the producer's output fields:
   - Requirements are values the consumer solved first: the consumer's `in.size == size` is solved within the consumer, then pushed to the producer as `out.size = …; rand_mode(0)`.
   - If the producer's own constraints reject those values, try another producer type.

**Registering producers is automatic.** Declaring `fw_output #(B)` in an action type is enough to register that type as a producer of `B` through static registration. Nobody writes a producer list (minimal user spec).

**Streams** follow the same rules, except that an inferred producer is *forked* alongside the consumer and they meet at the stream.

**What Tier 0 doesn't do:**
- infer a producer *earlier* than just in time,
- share one inferred producer among several consumers,
- choose a producer because it helps a constraint further downstream.

### 4.3 State inference

- The state pool holds the current value.
- The consumer states its requirement in one of two ways: as values (parameters) or as a predicate method, `virtual function bit accepts(S s)`.
- If the current state is accepted, proceed. While the action reads the state, the state is locked.
- Otherwise, try registered transition actions with the target passed as parameters to their output, or randomize and keep only accepted results.
- **One step works at Tier 0. Multi-step chains are planning.** A small breadth-first search, bounded in depth, over the registered transitions is feasible at Tier 1. Doing it properly needs Tier 2. This is the clearest part of the 10–20%.

### 4.4 Containers

- **`fw_parallel`:** add members, then `run()`. It optionally holds back members' resource grants and inference decisions until every member has registered, so it can see all its outputs before anything starts.
- **`fw_schedule`:** shuffles start order and adds bounded random start jitter. Members still wait on resources and data dependencies, so any order we reach is legal by construction. It records the order it used for coverage.
- **`fw_select`:** works through weighted branches whose guards hold. If a branch can't be solved, it moves to the next. It records the branch it chose.
- **The `fork` style can see the whole group too.** Branches can register with an `fw_scope` that waits one delta cycle (`#0`) until the expected number of members have registered. That would give lookahead to the `` `fw_do_with `` style as well. Worth a prototype; not essential.

## 5. Recovering the global part

### 5.1 Tier 1: build, then plan, then run

**What the planner gets:** if the user builds the whole container tree and then calls `root.run()`, the tree is *data* before execution. A planner can walk it and:
- check legality statically (lock conflicts in `parallel`),
- infer ahead of time and share producers,
- run a bounded state search,
- choose a random legal `schedule` order.

**What it needs:**
- no solver changes,
- only the tree, plus the outputs and claims each action type declares.

### 5.2 Tier 2: solve the built tree globally with dv-solve

**Why it's feasible:** constraints in SV classes can't be inspected at run time, but the *action types are static*. fw-hdl-fe-sv already lowers SV classes to Zuspec IR, so each action type's constraints can be compiled into a dv-solve blob.

**How the solve is built:**
- The tree built at run time supplies the *structure*: which actions, which handles, and which flow bindings.
- The runtime puts together a problem for the scope:
  - each member's blob,
  - an equality between the fields of each producer output and the consumer input it feeds,
  - candidate sets for component and resource choices,
  - attached policies (they're classes too, so they compile).
- It solves the problem through DPI. This is what `ScScopeProblem` and `ScBufferPick` already describe.

**What it gives:**
- backward propagation from consumer to producer,
- inference chosen to suit downstream constraints,
- multi-step state chains (fixed depth, unrolled),
- infeasibility found before anything runs.

**The rule that makes it work: programmatic structure, static constraints.** It also fits the review's "one solver everywhere" (§4.5): randomizing through dv-solve in the SV runtime means Tier 2 adds nothing new to install.

### 5.3 Lifting into Zuspec IR

- **What can be lifted:** where the construction is statically shaped (container calls whose members are constant, loops with constant bounds), fw-hdl-fe-sv can recognize the builder API and emit `ActivityParallel`, `ActivitySchedule` and the other activity nodes directly.
- **What lifting gives:** `pss_lower` then provides full PSS semantics. `zuspec-be-sw` emits the scenario as host C++ or C for emulation and the system model (review §4.5 and §4.6).
- **Why the API must stay narrow:** this is the portability story applied to scenarios, and the reason the builder API should be *narrow and recognizable*:
  - a small fixed set of container classes and macros,
  - no clever wrappers that hide structure.
- **Dynamic code still works.** Code the front end can't lift still runs at Tier 0 or 1 in SV. It just doesn't port to the host.

## 6. What we need to build

1. **A `fw-dv-spec` scenario chapter.** It defines:
   - the action lifecycle (create → bind component → claim → solve → body → release),
   - container semantics and join specs,
   - pool resolution order (§4.2),
   - parameter semantics,
   - which parts of PSS are deliberately weaker at each tier.

   The SV runtime, C++ host and Python harness all implement this one spec.
2. **A runtime in `fw-dv-rt-sv`:**
   - classes: `fw_action #(C)`, `fw_parallel`, `fw_schedule`, `fw_select`, `fw_input`/`fw_output #(T)`, `fw_lock`/`fw_share #(R)`, and `fw_pool`/`fw_state_pool`;
   - macros: `` `fw_do ``, `` `fw_do_with ``, `` `fw_set ``, `` `fw_policy ``.

   Pools are a *capability* attached to components, not methods on `fw_component` (see memory: capability layers).
3. **sv-weave generation:**
   - a typed `with_(...)` parameter constructor per action,
   - automatic producer registration from declared outputs,
   - policy classes from annotations.
4. **Recording:**
   - every traversal, inference decision, chosen select branch, schedule order, claim and wait goes into the trace format from review §4.6;
   - "why did this action run?" (inferred for X) is the scenario version of the cause-and-effect links described there;
   - scenario coverage comes from the same records.
5. **Tier 1 planner** (SV only).
6. **Tier 2:**
   - randomize through dv-solve in the SV runtime,
   - assemble the scope problem from per-type blobs,
   - align with `ScScopeProblem`.
7. **Builder recognition in fw-hdl-fe-sv** for the lifted path.
8. **Python:** the same API shape in the Python harness (review §4.6, `zuspec-dataclasses` `traverse`), so scenarios can drive the system model.

## 7. Open issues

1. **Naming.** `fw_do` versus `traverse` versus `run`. The Python notes use `traverse`. Pick one name across SV, C++ and Python.
2. **Parameter syntax.** `with_(...)` generated per action, versus a generic `` `fw_set ``. How do we express "unset" for optional parameters? (A per-field flag, or always use `rand_mode`.)
3. **Already-solved handles.** How does the runtime know a child was solved by its parent and must not be randomized again? Proposal: a flag set in the parent's `post_randomize`, cleared after `body`.
4. **Binding-dependent constraints on declared handles.** Are candidate-set fields for `comp` and `instance_id` (§3.2, item 2) enough, or do we need a two-phase solve?
5. **Lock conflicts in `parallel`.** Serialize (the default) or raise an error (`strict`)? What should Tier 1 report?
6. **Inference policy knobs.** Producer weights, the maximum inference depth, and whether to reuse or always create objects. Where do they live: the pool, the test, or factory-like configuration?
7. **State pools under concurrency.** How long the read lock is held, and whether a consumer re-checks after waiting.
8. **Tier 2 dependency.** It needs SV randomization to go through dv-solve. Do we keep SV's native solver as a fallback for constructs dv-solve doesn't support, and how do we report which solver handled each action?
9. **How much to lift.** Exactly which builder patterns fw-hdl-fe-sv recognizes, and whether code that can't be lifted is an error or a warning when a host target is requested.
10. **Timing.** All of this sits on the fw-dv core (lifecycle, components, recording), V1 in the review's phasing. Scenarios are a natural V2.5: after portable content and before the host C++ work (V5) that consumes them.
