# Session & Browser Window — Manual Test Plan

Test the binding between Claude Code sessions and browser windows.

## Setup

Kill any existing server so we start clean:

```bash
pkill -f "buckaroo.server" || true
```

Create two test files:

```bash
echo "name,age,city\nAlice,30,NYC\nBob,25,LA\nCharlie,35,Chicago" > /tmp/test_a.csv
echo "product,price,qty\nWidget,9.99,100\nGadget,24.50,50\nDoohickey,3.75,999" > /tmp/test_b.csv
```

---

## Test 1: First view_data call

In **Claude Code window 1**, say:

> use view_data on /tmp/test_a.csv

**Observe and report:**
- Did a browser tab or window appear?
- Was it a new window, or a new tab in an existing Chrome window?
- What's the URL in the address bar?
- Does the table show Alice/Bob/Charlie?

---

## Test 2: Second view_data, same session, different file

Stay in **Claude Code window 1**, say:

> use view_data on /tmp/test_b.csv

**Observe and report:**
- Did a NEW tab/window open, or did the existing one update?
- Did the existing tab get focused/brought to front?
- Does it now show Widget/Gadget/Doohickey?
- Did you have to click anything, or did it just appear?

---

## Test 3: Bury the tab, then trigger again

Click away from the Buckaroo tab — open a few other tabs in Chrome, switch to one of them. Maybe even minimize the Chrome window or switch to a different app.

Back in **Claude Code window 1**, say:

> use view_data on /tmp/test_a.csv

**Observe and report:**
- Did Chrome come to the foreground?
- Did the correct tab get activated (not some other tab)?
- Or did a duplicate tab/window get created?

---

## Test 4: Second Claude Code session

Open **Claude Code window 2** (a completely separate `claude` invocation in a new terminal). Say:

> use view_data on /tmp/test_b.csv

**Observe and report:**
- Did a NEW browser tab/window appear (separate from window 1's tab)?
- Or did it hijack window 1's tab?
- What's the URL — is the session ID different from window 1's URL?
- Are both tabs/windows now accessible?

---

## Test 5: Cross-session interference check

With both Claude Code windows open, go back to **Claude Code window 1** and say:

> use view_data on /tmp/test_a.csv

**Observe and report:**
- Did it focus window 1's original tab (the one showing test_a)?
- Did window 2's tab change at all?
- How many total Buckaroo tabs/windows exist now?

---

## Test 6: Close the browser tab, then trigger

Manually close the Buckaroo tab for **window 1** (click the X on the tab).

In **Claude Code window 1**, say:

> use view_data on /tmp/test_a.csv

**Observe and report:**
- Did a new tab/window get created to replace the closed one?
- Or did nothing visible happen?

---

## Test 7: Check what browser was used

**Report:**
- What is your default browser? (Chrome, Arc, Safari, Firefox?)
- If not Chrome, did anything open at all?
- Did you see the URL in Claude Code's response text? (the "Interactive view: http://..." line)

---

## Bonus: Check the server state

Run this in any terminal:

```bash
curl -s http://localhost:8700/health
```

and:

```bash
ps aux | grep buckaroo.server
```

Report whether the server is still running and how many server processes exist.

---

## What we're looking for

| # | Question | Desired behavior |
|---|----------|-----------------|
| 1 | Tab vs window | Dedicated window per session (not a tab in existing window) |
| 2 | Reuse vs duplicate | Same session reuses its window, shows new data |
| 3 | Focus reliability | Brings the correct tab forward from behind other tabs/apps |
| 4 | Session isolation | Two Claude Code windows get separate browser tabs |
| 5 | Cross-session safety | Focusing session 1 doesn't affect session 2's tab |
| 6 | Recovery from closed tab | Recreates the window if user closed it |
| 7 | Browser compatibility | Works with user's actual default browser |
