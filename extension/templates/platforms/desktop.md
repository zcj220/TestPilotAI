<!-- TestPilot-Template-Version: 16 -->
# Platform Blueprint Rules (platform = "desktop")

> This file defines all rules for Windows desktop application blueprints.
> AI coding assistants MUST read this file completely before generating any blueprint content.

---

## ZERO: Read Source Code First (Mandatory Pre-Step)

**Before writing any blueprint, follow these steps in order:**

1. Run the application and observe the window title bar  copy the exact window title for `window_title`
2. Look at every control's visible text label on screen  copy exactly for `name:` selectors
3. Check XAML/source files for `AutomationId` attributes  prefer these over `name:` if available
4. Read all business logic to know exact success/error states and what text changes on screen
5. Read all async code to estimate actual delay times for wait values

**Why this matters:** `name:` selectors must match the EXACT visible text on screen, no more, no less. "Login"  "Login Button"  "Login  " (with space).

---

## ONE: Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | YES | Must be `"desktop"` |
| `window_title` | YES | Exact text of the application window title bar |
| `base_url` | YES | Must be `""` (empty string) |
| `app_name` | YES | Display name |
| `description` | YES | 50-200 chars: what the app does and what scenarios are covered |
| `start_command` | NO | e.g. `"MyApp.exe"`  if engine should launch the app |
| `start_cwd` | NO | Working directory for `start_command` |

---

## TWO: Available Actions

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `value` (window title) | Attach to or launch the application window |
| `click` | `target` (selector) | Click a UI control |
| `fill` | `target`, `value` | Clear and type text into an input control |
| `wait` | `value` (ms) | Fixed wait in milliseconds |
| `assert_text` | `expected` | Assert window or control contains this text |
| `screenshot` |  | Take a screenshot |

---

## THREE: Selector Rules

### Primary Selector: name:visible-text

The `name:` selector targets controls by their visible text label on screen.

**Format:** `name:ExactVisibleText`

**Critical rule:** The text after `name:` must be EXACTLY what appears on screen  no extra words, no type suffixes.

```
CORRECT: name:Login
WRONG:   name:Login Button        (do not add "Button")
WRONG:   name:Username            (for an EditBox labeled "Username:")   use just: name:Username
WRONG:   name:Login               (if actual screen text is "Log In" with space)
```

### Secondary Selector: automationid:xxx

If the XAML/source code sets an `AutomationId` or `Name` property on a control, use:

`automationid:ExactAutomationId`

This is more stable than `name:` because it doesn't change when the UI text is translated.

### 3-Step Validation Process

Before writing any selector, do ALL three steps:

1. **Look at the screen**  launch the app, find the control you need
2. **Copy visible text exactly**  character-for-character as it appears on screen
3. **Check for AutomationId**  look in XAML for `AutomationId="xxx"`  use that if available

### Absolutely Forbidden Selectors

- CSS selectors `#id` or `.class`  web selectors, NOT valid for desktop automation
- `accessibility_id:xxx`  mobile selector, NOT supported for Windows desktop
- Any mobile selector format (Android/iOS patterns)
- Appending type suffixes: `name:Login Button`, `name:用户名输入框`  these will FAIL

---

## FOUR: Transient UI  Cannot Be Asserted

| Component | Why it cannot be asserted |
|-----------|--------------------------|
| System tray notification | Bubble popup, disappears after a few seconds |
| Splash screen | Startup screen, gone after app loads |
| Status bar transient message | Short message, reverts to normal state |
| ToolTip | Appears on hover, disappears when mouse moves |

**Persistence validation guide:**
```
CAN assert:
  Window title bar text
  Button / label text that stays visible
  List items, table cells
  Status bar text that is permanently set

CANNOT assert:
  Bubble notifications
  Splash screen text
  ToolTip text
```

---

## FIVE: Wait Time Formula

```
wait = operation_time + 1500ms  (buffer for window refresh + UI Automation system response)
```

| Scenario | Recommended wait |
|----------|-----------------|
| Cold start (after navigate) | wait 3000-5000 (depends on app size) |
| Child window / dialog opening | wait 1500 |
| File read/write operation | wait 2000 |
| Network request | API_time + 1500 |
| UI control interaction (local) | wait 1000 |

---

## SIX: Scenario Isolation Principle and Flow Mode

### Mandatory Flow Decision for Every Page

**Check these rules in order when generating scenarios for each `page`:**

1. Does this page have 2 scenarios that ALL require login first?  **MUST set `"flow": true`**
2. Does this page have 2 scenarios that are sequential menu operations or multi-tab switching?  **MUST set `"flow": true`**
3. Do scenarios need independent clean state (e.g. correct login vs wrong login)?  No flow (default `false`)

### Default Mode (flow: false)

- Engine may restart the application between scenarios
- Each scenario should start with `navigate` (attach/launch app) + `wait` (startup time)
- If scenario requires a specific pre-state (e.g. logged in), it MUST perform those actions itself
- **FORBIDDEN** to share state between scenarios

### Flow Mode (flow: true)

Set `"flow": true` at the `page` level. Scenarios run sequentially:
- Only the 1st scenario's `navigate` actually attaches/launches the app
- Subsequent `navigate` steps are auto-skipped by engine
- Window state preserved between scenarios
- If 3 consecutive scenarios fail  engine attempts restart recovery, then continues
- Each scenario must still include `navigate` (for independent running)

### CRITICAL: Non-First Scenario Rules in Flow Mode

**In flow mode, scenarios #2, #3, etc. must ONLY have: navigate + that scenario's own operations. NEVER repeat login steps.**

If step 2 of a non-first scenario is `fill Username`, but the app is already on the main window (logged in from scenario 1), the input field is NOT FOUND  timeout  3 consecutive failures  scenario aborted  chain of failures.

| WRONG | CORRECT |
|-------|---------|
| navigate  wait  fill Username  fill Password  click Login  wait  actual ops | navigate  actual ops  assert_text |

**Rule: In flow mode, only the FIRST scenario does the full startup + login. All others start directly with their own operations.**

---

## SEVEN: Setup — Reusable Navigation Paths

When 3+ scenarios share the same prefix steps (e.g. app launch → login → navigate to module), extract them into `setups`.

- Define each navigation path once in `"setups"` at the top level
- Reference it via `"setup": "name"` in each scenario
- Use `"extends": "parent_name"` to chain paths (e.g. `enter_settings` extends `login`)
- The engine resolves the full chain and prepends all steps before the scenario’s own steps
- Max 3 levels of extends; no circular references

---

## EIGHT: Complete JSON Template

```json
{
  "app_name": "Your App Name",
  "description": "50-200 char description of features and test coverage",
  "base_url": "",
  "platform": "desktop",
  "setups": {},
  "window_title": "Exact Window Title Here",
  "start_command": "MyApp.exe",
  "start_cwd": "D:/Apps/MyApp",
  "pages": [
    {
      "url": "",
      "name": "Main Window",
      "flow": true,
      "scenarios": [
        {
          "name": "Valid login → main view (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "Exact Window Title Here", "description": "Launch or attach to application window"},
            {"action": "wait", "value": "3000", "description": "Wait for app window to fully load"},
            {"action": "fill", "target": "name:Username", "value": "testuser", "description": "Type username (replace with actual test data)"},
            {"action": "fill", "target": "name:Password", "value": "pass1234", "description": "Type password (replace with actual test data)"},
            {"action": "click", "target": "name:Login", "description": "Click Login button (replace with actual visible text)"},
            {"action": "wait", "value": "2000", "description": "Wait for login validation and view switch"},
            {"action": "assert_text", "expected": "Welcome", "description": "Verify main view shows welcome message"},
            {"action": "screenshot", "description": "Main view after login"}
          ]
        },
        {
          "name": "Add new item (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "Exact Window Title Here", "description": "Flow mode: navigate auto-skipped, already on main view"},
            {"action": "click", "target": "name:Add", "description": "Click Add button (replace with actual visible text)"},
            {"action": "wait", "value": "1500", "description": "Wait for dialog to open"},
            {"action": "fill", "target": "name:Name", "value": "Sample Item", "description": "Enter name (replace with actual test data)"},
            {"action": "click", "target": "name:Save", "description": "Click Save (replace with actual visible text)"},
            {"action": "wait", "value": "1000", "description": "Wait for save and list refresh"},
            {"action": "assert_text", "expected": "Sample Item", "description": "Verify item appears (replace with actual expected text)"},
            {"action": "screenshot", "description": "List after adding item"}
          ]
        }
      ]
    }
  ]
}
```

---

## NINE: Checklist

### Pre-Generation Checklist
- [ ] If 3+ scenarios share login/navigation steps, extracted them into `setups`
- [ ] Launched app and verified `window_title` matches exactly
- [ ] All `name:` selectors use only the visible screen text (no extra words)
- [ ] Checked for `AutomationId` in XAML  used `automationid:xxx` where available
- [ ] `base_url` is `""`
- [ ] `expected` text is permanently visible in control (not tooltip/notification)
- [ ] Adequate wait after navigate for startup

### MANDATORY Post-Generation Checks (3 required  fix if any fail)

**Check 1  Flow decision:** For each page with 2 scenarios that ALL require login first:
- YES  that page MUST have `"flow": true` AND non-first scenarios MUST NOT contain login steps
- NO  no flow needed (each scenario independently starts up and logs in)

**Check 2  Assert coverage:** For every scenario, does it have at least one `assert_text` step?
- Screenshot alone is NOT sufficient  must have text assertion
- `expected` must be text that is permanently visible in a UI control

**Check 3  Duplicate login check:** Are there 3 scenarios with identical login step sequences?
- YES  merge those scenarios into one page with `"flow": true`, login only once in first scenario

---

## TEN: Gotcha Table

| Mistake | Consequence | Correct Approach |
|---------|-------------|-----------------|
| `name:Login Button` | Control not found (screen shows "Login" only) | `name:Login`  exact visible text only |
| `name:Username input field` | Not found | `name:Username`  no type suffix |
| CSS selector `#id` | Not supported for desktop | Use `name:text` or `automationid:xxx` |
| `accessibility_id:xxx` | Mobile selector, not for desktop | Use `name:text` or `automationid:xxx` |
| No wait after navigate | Window not ready, controls not loaded | wait 3000-5000 after cold start |
| `window_title` with typo | Engine cannot find window | Copy title bar text character-by-character |

---

## ELEVEN: Page Coordinate Cache (Automatic — No Blueprint Changes Needed)

The engine uses a dual-strategy approach: **UI Automation first** (fast, precise) → **AI vision fallback** (screenshot + AI locates element coordinates). The AI vision results are cached so re-analysis is skipped on subsequent runs.

Cache file: `testpilot/.page_cache_desktop.json` (auto-created next to the blueprint file).

**How it works:**

| Run | What happens |
|-----|-------------|
| UI Automation succeeds | No screenshot needed, no cache used — control found instantly |
| UI Automation fails → first time on this page | Screenshot taken → AI analyzes pixel coordinates → saved to cache |
| UI Automation fails → same page again | Fingerprint match → **cached coordinates reused, AI skipped** |
| Window layout changes | Fingerprint mismatch → re-analyzes → overwrites that page's cache entry |

**Cache validation rules:**
- Validated by: `app_name` field in the blueprint
- If `app_name` changes: old cache is discarded automatically
- Cache file location: `testpilot/.page_cache_desktop.json`

**What this means for blueprints:**
- You do NOT need special steps to "enable" or "update" the cache — it is fully automatic
- The more precisely `window_title` is set, the more reliable UI Automation is (reducing AI vision calls overall)
- Cache persists across multiple test runs and across ALL blueprint files in the same `testpilot/` directory
- To force a full re-analysis (e.g. after major window layout redesign): delete `testpilot/.page_cache_desktop.json`
