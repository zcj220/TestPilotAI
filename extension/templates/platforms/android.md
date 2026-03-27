<!-- TestPilot-Template-Version: 10 -->
# Platform Blueprint Rules (platform = "android")

> This file defines all rules for Android/Flutter application blueprints.
> AI coding assistants MUST read this file completely before generating any blueprint content.

---

## ZERO: Read Source Code First (Mandatory Pre-Step)

**Before writing any blueprint, follow these steps in order:**

1. Read ALL Flutter widget files (.dart) or Android layout files (.xml) to find Semantics labels and accessibility identifiers
2. Read ALL navigation code to understand screen transitions and route names
3. Read ALL business logic to know exact success/error states and displayed text
4. Confirm `app_package` and `app_activity` from AndroidManifest.xml or build.gradle
5. Read ALL async code to estimate actual delay times for wait values

**Why this matters:** Flutter `Key` values are NOT Appium selectors. Do not guess accessibility labels  you MUST read the Semantics code.

---

## ONE: Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | YES | Must be `"android"` (Flutter apps too  NOT `"flutter"`) |
| `app_package` | YES | e.g. `"com.example.myapp"`  from AndroidManifest.xml |
| `app_activity` | YES | e.g. `".MainActivity"`  from AndroidManifest.xml |
| `base_url` | YES | Must be `""` (empty string)  native apps have no HTTP URL |
| `app_name` | YES | Display name |
| `description` | YES | 50-200 chars: what the app does and what scenarios are covered |

---

## TWO: Available Actions

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `value` (package/activity) | Restart app: force-stop then relaunch |
| `click` | `target` (selector) | Tap an element |
| `fill` | `target`, `value` | Clear and type text into an input field |
| `wait` | `value` (ms) OR `target`+`timeout_ms` | Fixed wait OR wait for element to appear |
| `assert_text` | `expected` | Assert element or page contains this text |
| `screenshot` |  | Take a screenshot |

**Two wait formats:**

| Format | Usage | Description |
|--------|-------|-------------|
| Fixed wait | `{"action": "wait", "value": "3000"}` | Wait exactly N milliseconds |
| Wait for element | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | Poll until element appears |

**Forbidden actions** (not supported for android): `navigate_to`, `evaluate`, `reset_state`

---

## THREE: Selector Rules

### Flutter Semantics  Android Accessibility Mapping

| Flutter Usage | Android Property | Blueprint Selector |
|---------------|-----------------|-------------------|
| `Semantics(label: 'xxx', button: true)` | `content-desc="xxx"` | `accessibility_id:xxx` |
| `Semantics(label: 'xxx', textField: true)` wrapping TextField | `hint="xxx"` | `//android.widget.EditText[@hint='xxx']` |
| `IconButton(tooltip: 'xxx')` | `content-desc="xxx"` | `accessibility_id:xxx` |
| `TextField(decoration: InputDecoration(hintText: 'xxx'))` | `hint="xxx"` | `//android.widget.EditText[@hint='xxx']` |
| `Semantics(label: 'xxx')` plain label (no button/textField) | `content-desc="xxx\nchild-text"` | `accessibility_id:xxx` (partial match) |

**Key rule:** When `Semantics(label: 'tf_user', textField: true)` wraps a `TextField(hintText: 'Enter name')`, the effective `hint` is `tf_user` (Semantics label OVERRIDES hintText).

### 3-Step Validation Process

Before writing any selector, do ALL three steps:

1. **Find in source**  open the .dart file, locate the Semantics/accessibilityIdentifier annotation
2. **Copy the label**  copy the `label` string or `hint` string exactly as written
3. **Choose the right format**  button/label  `accessibility_id:label`, input/textField  `//android.widget.EditText[@hint='label']`

### Selector Priority (use in this order)

| Priority | Format | When to use |
|----------|--------|------------|
| 1 | `accessibility_id:xxx` | Buttons, labels, icons with Semantics label or tooltip |
| 2 | `//android.widget.EditText[@hint='xxx']` | Text input fields (TextField/EditText) |
| 3 | `//ClassName[@attribute='value']` | Other elements via precise XPath |

### Absolutely Forbidden Selectors

- `id:xxx`  NOT the same as `accessibility_id:xxx`; do not use
- `#id` or `.class`  these are CSS selectors; NOT valid for native Android
- `UiSelector().className("xxx").instance(N)`  index-based; breaks when UI changes
- `//XPath[@index='N']`  same problem, index breaks on UI changes
- Flutter `Key` values  Keys are for Flutter widget tree only; Appium cannot use them

**Critical pitfall:** Do NOT guess button text. You MUST read the source code. A button labeled "Submit" in source might display "提交" on screen  always check actual text from `.dart` files.

---

## FOUR: Transient UI  Cannot Be Asserted

| Component | Why it cannot be asserted |
|-----------|--------------------------|
| `SnackBar` | Auto-dismisses after ~2-4s; element gone before assertion |
| `Toast` (Android system) | System-level overlay, not in accessibility tree |
| Loading overlay | Transient  gone after load completes |

**Rule:** Only assert text that is permanently visible in a screen widget. Check your source for `ScaffoldMessenger.of(context).showSnackBar(...)`  that text CANNOT be used in `assert_text`.

---

## FIVE: Wait Time Formula

```
wait = async_delay_in_code + 2000ms  (buffer for Flutter render + Appium U2 refresh)
```

| Scenario | Recommended wait |
|----------|-----------------|
| App cold start (after navigate) | wait 3000 |
| API call + widget rebuild | API_time + 2000 |
| Navigator.push / pushReplacementNamed | wait 2000 |
| setState() local update | wait 1000 |
| Widget animation completion | animation_time + 500 |

**After each `navigate` (force-stop + relaunch), always do:** `wait 3000` then `wait target element` to confirm ready.

---

## SIX: Scenario Isolation Principle and Flow Mode

### Mandatory Flow Decision for Every Page

**Check these rules in order when generating scenarios for each `page`:**

1. Does this page have 2 scenarios that ALL require login first?  **MUST set `"flow": true`**
2. Does this page have 2 scenarios that are sequential screen transitions or continuous operations?  **MUST set `"flow": true`**
3. Do scenarios need independent clean state (e.g. correct login vs wrong login)?  No flow (default `false`)

### Default Mode (flow: false)

- `navigate` value = `"com.example.app/.MainActivity"` (package + activity)
- Engine executes: `adb shell am force-stop {package}`  creates new Appium session  relaunches app
- `@Published` / `setState` variables reset on cold start
- Persistent storage (SharedPreferences, SQLite) does NOT reset
- Each scenario MUST start with `navigate` + `wait 3000`
- **FORBIDDEN** to share state between scenarios

### Flow Mode (flow: true)

Set `"flow": true` at the `page` level. Scenarios run sequentially:
- Only the 1st scenario's `navigate` actually force-stops and relaunches
- Subsequent `navigate` steps are auto-skipped by engine
- App state preserved between scenarios
- If 3 consecutive scenarios fail  engine force-stops and recovers, then continues
- Each scenario must still include `navigate` (for independent running)

### CRITICAL: Non-First Scenario Rules in Flow Mode

**In flow mode, scenarios #2, #3, etc. must ONLY have: navigate + that scenario's own operations. NEVER repeat login steps.**

If step 2 of a non-first scenario is `fill username`, but the app is already on the home screen (logged in from scenario 1), the EditText is NOT FOUND  timeout  3 consecutive failures  scenario aborted  chain of failures.

| WRONG | CORRECT |
|-------|---------|
| navigate  wait  fill username  fill password  click login  wait  actual ops | navigate  actual ops  assert_text |

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
  "platform": "android",
  "setups": {},
  "app_package": "com.example.myapp",
  "app_activity": ".MainActivity",
  "pages": [
    {
      "url": "",
      "name": "Login Screen",
      "flow": true,
      "scenarios": [
        {
          "name": "Valid login → navigates to home (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "com.example.myapp/.MainActivity", "description": "Cold start: force-stop then relaunch app"},
            {"action": "wait", "value": "3000", "description": "Wait for app startup, first-frame render takes 2-3s"},
            {"action": "wait", "target": "accessibility_id:btn_login", "timeout_ms": 10000, "description": "Wait until login button is visible"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='tf_username']", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='tf_password']", "value": "pass1234", "description": "Enter password (replace with actual test data)"},
            {"action": "click", "target": "accessibility_id:btn_login", "description": "Tap login button (replace selector with actual accessibility_id)"},
            {"action": "wait", "value": "3000", "description": "Wait for API response and screen transition"},
            {"action": "assert_text", "expected": "Welcome", "description": "Verify home screen text (replace with actual text from source code)"},
            {"action": "screenshot", "description": "Home screen after login"}
          ]
        },
        {
          "name": "Invalid login → error shown (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "com.example.myapp/.MainActivity", "description": "Flow mode: navigate auto-skipped for non-first scenario"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='tf_username']", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='tf_password']", "value": "wrong", "description": "Enter wrong password"},
            {"action": "click", "target": "accessibility_id:btn_login", "description": "Tap login, API returns error"},
            {"action": "wait", "value": "2000", "description": "Wait for error response"},
            {"action": "assert_text", "expected": "Error", "description": "Verify error text (replace with actual error text from source code)"},
            {"action": "screenshot", "description": "Login error state"}
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
- [ ] Read all .dart files, confirmed Semantics labels and hint text
- [ ] Confirmed `app_package` from AndroidManifest.xml
- [ ] Confirmed `app_activity` from AndroidManifest.xml
- [ ] `base_url` is `""`
- [ ] All input selectors use `//android.widget.EditText[@hint='xxx']`
- [ ] All button selectors use `accessibility_id:xxx`

### MANDATORY Post-Generation Checks (3 required  fix if any fail)

**Check 1  Flow decision:** For each page with 2 scenarios that ALL require login first:
- YES  that page MUST have `"flow": true` AND non-first scenarios MUST NOT contain login steps
- NO  no flow needed (each scenario independently cold-starts)

**Check 2  Assert coverage:** For every scenario, does it have at least one `assert_text` step?
- Screenshot alone is NOT sufficient  must have text assertion
- `expected` must be text permanently visible in a widget (not SnackBar/Toast)

**Check 3  Duplicate login check:** Are there 3 scenarios with identical login step sequences?
- YES  merge those scenarios into one page with `"flow": true`, login only once in first scenario

---

## TEN: Gotcha Table

| Mistake | Consequence | Correct Approach |
|---------|-------------|-----------------|
| Using `id:xxx` instead of `accessibility_id:xxx` | Element not found | Use `accessibility_id:xxx` |
| Using CSS selector `#id` or `.class` | SyntaxError  not valid for native Android | Use `accessibility_id` or XPath |
| Flutter Key as selector | Not found  Keys are not Appium selectors | Use Semantics label |
| XPath with `@index` | Breaks when UI reorders | Use attribute-based XPath |
| Guessing button text without reading source | Wrong text, element not found | Read .dart files for actual text |
| No wait after navigate | App not ready, elements not yet rendered | Always `wait 3000` after navigate |
| Asserting SnackBar text | Flaky  SnackBar already dismissed | Assert permanently visible widget text |
| Semantics label OVERRIDING hintText | Wrong hint selector | Check which label/hint is effective |

---

## ELEVEN: Page Coordinate Cache (Automatic — No Blueprint Changes Needed)

The engine automatically manages a persistent page coordinate cache at `testpilot/.page_cache.json`.

**How it works:**

| Run | What happens |
|-----|-------------|
| First run on a new page | Engine takes a screenshot + calls AI to locate elements → coordinates saved to cache |
| Subsequent runs on same page | Engine dumps UI tree → computes fingerprint → cache hit → **reuses coordinates, skips screenshot + AI** |
| Page UI changes | Fingerprint mismatch → re-analyzes → overwrites that page's cache entry |

**Cache validation rules:**
- Validated by: device screen resolution + `app_package` (or `bundle_id` for iOS)
- If device or package changes: old cache is discarded automatically
- Cache file location: `testpilot/.page_cache.json` (auto-created next to the blueprint file)

**What this means for blueprints:**
- You do NOT need special steps to "enable" or "update" the cache — it is fully automatic
- First test run is slower (AI analysis per new page); subsequent runs are faster (cache reuse)
- The cache persists across multiple test runs and across ALL blueprint files in the same `testpilot/` directory
- To force a full re-analysis (e.g. after major UI redesign): delete `testpilot/.page_cache.json`
- **Do not gitignore `.page_cache.json`** — keeping it in source control lets teammates reuse the same coordinates without re-running AI analysis
