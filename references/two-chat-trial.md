# Two-chat trial: Harbor Switch

Run this in two fresh empty project folders with the same model, reasoning
effort, browser, permissions and time/credit cap. For example, use GitHub
Copilot GPT-6 Luna at `low` in both. Install and explicitly invoke HarrTest in
only one chat; check that it is not loaded in the control. Keep the same
normal tool and skill access otherwise. Leave the scoring guide out of both
generation prompts. Do not repair one output before recording both.

## Copy the same task into both chats

```text
Build Harbor Switch, a playable 3D browser game about a small dockside rail
trolley delivering one sealed cargo crate at blue hour. The whole game should
be one compact, replayable job. Start stopped in the marked approach zone
with a visible fork. The switch initially leads to a service siding, not the
cargo berth. The player must route the trolley to the berth, stop, and unload.

Controls: W accelerates, S brakes, E changes the switch only while stopped in
the marked approach zone, F unloads only while stopped at the cargo berth,
and R resets the whole job at any time. A wrong siding never completes the
job. The route indicator must agree with the physical switch. Show why a
switch or unload action was rejected. On success, the crate visibly moves
from the trolley to the berth. Reset restores the loaded crate, initial
route, stationary trolley and HUD, even after a successful delivery.

Use a readable rear three-quarter gameplay camera. Make a recognizable
low-slung trolley with fitted wheels and hubs, an underframe and secured
cargo. Wheels should track the rails and visibly roll and stop with the
trolley. Make the fork, moving switch points and route signals legible
during play. Give the berth and service siding distinct silhouettes. Use
cool dock lighting and warm signal lamps, and keep the trolley and rails
readable. The HUD should show controls, selected route and delivery state
without covering the switch or trolley.

Deliver runnable source in this checkout, with a localhost run command and
no remote services or assets at runtime. Run the actual game at 1440x900.
Save original browser screenshots of the loaded trolley at the approach
zone after switching to the berth, and of the finished delivery. Report
what you actually checked, where the evidence is, and anything unverified.
```

## Compare after both chats finish

Open the two approach screenshots without labels first. Then run the same
steps yourself: try `E` outside the zone and while moving; travel down the
default siding and try `F`; reset, select the berth while stopped, then try
`F` while moving and stopped at the berth; reset after success and deliver
again. Don't infer movement quality from a still.

| Detail | Look at the product | Look for in the review |
| --- | --- | --- |
| Trolley | Wheels fit the mounts and meet the rails; body and cargo read at gameplay scale. | Evidence of the actual wheel contact and motion, not just a mesh count or an idle screenshot. |
| Switch | Points, selected signal and actual travel agree; the wrong siding cannot finish. | Checks for both routes and for a moving or out-of-zone toggle. |
| Berth and lighting | The two destinations are distinguishable; lamps, rails and HUD remain readable during play. | At least one real approach view and a check of the side track, not just a title screen. |
| Delivery and reset | Cargo visibly unloads only when allowed; a reset restores it and permits a second delivery. | Evidence of a rejected unload, a successful unload, and a complete replay after reset. |

For each row, record **product observed** and **review evidence present**
separately. Mark anything you cannot verify as unverified. If a chat used
workers, look for a concrete handoff, disjoint edit scope, independent QA,
and any finding returned to the original owner. Agent count or a written
claim is not proof. Note time and credit use; a one-off trial is a comparison
of these two runs, not a general effectiveness or release test.
