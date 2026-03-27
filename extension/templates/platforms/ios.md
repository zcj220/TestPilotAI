<!-- TestPilot-Template-Version: 10 -->
# Platform Blueprint Rules (platform = "ios")

> This file defines all rules for iOS/SwiftUI application blueprints.
> AI coding assistants MUST read this file completely before generating any blueprint content.
> Note: iOS testing via Appium + XCUITest is only supported on macOS.

---

## ZERO: Read Source Code First (Mandatory Pre-Step)

**Before writing any blueprint, follow these steps in order:**

1. Read ALL SwiftUI view files (.swift) to find `.accessibilityIdentifier("xxx")` annotations
2. Read ALL navigation code (NavigationLink, .sheet, .fullScreenCover) to understand screen flow
3. Read ALL business logic and API calls to know success/error states and displayed text
4. Confirm `bundle_id` from the Xcode project settings (Info.plist or project.pbxproj)
5. Read ALL async code to estimate actual delay times for wait values

**Why this matters:** If `.accessibilityIdentifier()` is not set on an element, XCUITest CANNOT locate it. You MUST read the source first.

---

## ONE: Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | YES | Must be `"ios"` |
| `bundle_id` | YES | e.g. `"com.example.myapp"`  from Xcode project settings |
| `base_url` | YES | Must be `""` (empty string)  native apps have no HTTP URL |
| `app_name` | YES | Display name |
| `description` | YES | 50-200 chars: what the app does and what scenarios are covered |
| `udid` | NO | Device UDID  required only if multiple devices connected; omit for auto-detect |

---

## TWO: Available Actions

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `value` (Bundle ID) | Cold start: terminateApp then launchApp |
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

---

## THREE: Selector Rules

### SwiftUI accessibilityIdentifier  XCUITest Mapping

| SwiftUI Usage | XCUITest Property | Blueprint Selector |
|---------------|------------------|-------------------|
| `.accessibilityIdentifier("xxx")` on any view | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `TextField(...).accessibilityIdentifier("tf_x")` | `accessibility id = "tf_x"` | `accessibility_id:tf_x` |
| `SecureField(...).accessibilityIdentifier("tf_x")` | `accessibility id = "tf_x"` | `accessibility_id:tf_x` |
| `Button("text").accessibilityIdentifier("btn_x")` | `accessibility id = "btn_x"` | `accessibility_id:btn_x` |
| `Text("str").accessibilityIdentifier("lbl_x")` | `accessibility id = "lbl_x"` | `accessibility_id:lbl_x` |

**Naming convention:** Use prefixes: `btn_` (buttons), `tf_` (text fields), `lbl_` (labels), `list_` (lists)

### 3-Step Validation Process

Before writing any selector, do ALL three steps:

1. **Find in source**  open the .swift file, locate the view with `.accessibilityIdentifier("xxx")`
2. **Copy the identifier**  copy the string exactly as written in the modifier
3. **Write selector**  use `accessibility_id:` prefix followed by the exact identifier string

### Absolutely Forbidden Selectors

- CSS selectors `#id` or `.class`  web selectors, NOT valid for native iOS
- Android-style `accessibility_id:xxx` with Android resource-id format  different semantics on iOS but format IS the same (`accessibility_id:` is correct)
- `//XCUIElementTypeCell[N]`  index-based; breaks when UI reorders
- Pure type selectors without attributes: `//XCUIElementTypeButton`  matches ALL buttons
- NOT having `.accessibilityIdentifier()` on the element  XCUITest cannot locate it at all

### SwiftUI Code Requirement

**You MUST add `.accessibilityIdentifier()` to ALL interactive elements** before writing the blueprint. If the modifier is missing, XCUITest cannot locate the element.

```swift
// CORRECT  has accessibilityIdentifier
TextField("Username", text: $username)
    .accessibilityIdentifier("tf_username")
SecureField("Password", text: $password)
    .accessibilityIdentifier("tf_password")
Button("Login") { login() }
    .accessibilityIdentifier("btn_login")
Text(errorMessage)
    .accessibilityIdentifier("lbl_error")

// WRONG  no accessibilityIdentifier, XCUITest cannot find these
TextField("Username", text: $username)
Button("Login") { login() }
```

---

## FOUR: Transient UI  Cannot Be Asserted

| Component | Why it cannot be asserted |
|-----------|--------------------------|
| SwiftUI `.alert()` with auto-dismiss | Timer-based dismiss; element gone before assertion |
| `UIAlertController` auto-dismiss | System alert that disappears quickly |
| 3rd-party Toast / HUD | Transient overlay, not in XCUITest element tree |

**`.alert()` / `.sheet()` needs `wait 800` after trigger** to allow animation to complete before operating on elements inside the popup.

**Persistence validation guide:**
```
CAN assert:
  NavigationTitle("Record Book")      expected: "Record Book"
  Text("Welcome back")                expected: "Welcome back"
  Label with .accessibilityIdentifier("lbl_error") visible persistently

CANNOT assert:
  Alert with auto-dismiss timer
  3rd-party HUD/Toast transient overlay
```

---

## FIVE: Wait Time Formula

```
wait = async_delay_in_code + 2000ms  (buffer for SwiftUI render + XCUITest refresh)
```

| Scenario | Recommended wait |
|----------|-----------------|
| App cold start (after navigate) | wait 3000 |
| `.sheet()` / `.alert()` open animation | wait 800 |
| API call + UI rebuild (`@Published`) | API_time + 2000 |
| `@Published` property change + re-render | wait 1500 |
| NavigationLink page transition | wait 1500 |

**After each `navigate` (terminateApp + launchApp), always do:** `wait 3000` then `wait target element` to confirm ready.

---

## SIX: Scenario Isolation Principle and Flow Mode

### Mandatory Flow Decision for Every Page

**Check these rules in order when generating scenarios for each `page`:**

1. Does this page have 2 scenarios that ALL require login first?  **MUST set `"flow": true`**
2. Does this page have 2 scenarios that are sequential transitions or continuous tab operations?  **MUST set `"flow": true`**
3. Do scenarios need independent clean state (e.g. correct login vs wrong login)?  No flow (default `false`)

### Default Mode (flow: false)

- `navigate` value = Bundle ID (e.g. `"com.example.myapp"`)
- Engine executes: `mobile: terminateApp`  `mobile: launchApp` (cold start)
- `@Published` and `@State` variables reset after terminateApp
- `@AppStorage` (UserDefaults) does NOT reset  it is persistent storage
- Each scenario MUST start with `navigate` + `wait 3000`
- **FORBIDDEN** to share state between scenarios

### Flow Mode (flow: true)

Set `"flow": true` at the `page` level. Scenarios run sequentially:
- Only the 1st scenario's `navigate` actually terminates and relaunches
- Subsequent `navigate` steps are auto-skipped by engine
- App state preserved between scenarios
- If 3 consecutive scenarios fail  engine terminates, relaunches, recovers, then continues
- Each scenario must still include `navigate` (for independent running)

### CRITICAL: Non-First Scenario Rules in Flow Mode

**In flow mode, scenarios #2, #3, etc. must ONLY have: navigate + that scenario's own operations. NEVER repeat login steps.**

If step 2 of a non-first scenario is `fill tf_username`, but the app is already on the home screen (logged in from scenario 1), the TextField is NOT FOUND  timeout  3 consecutive failures  scenario aborted  chain of failures.

| WRONG | CORRECT |
|-------|---------|
| navigate  wait  fill tf_username  fill tf_password  click btn_login  wait  actual ops | navigate  actual ops  assert_text |

**Rule: In flow mode, only the FIRST scenario does the full cold-start + login. All others start directly with their own operations.**

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
  "platform": "ios",
  "setups": {},
  "bundle_id": "com.example.myapp",
  "udid": "",
  "pages": [
    {
      "url": "",
      "name": "Login Screen",
      "flow": true,
      "scenarios": [
        {
          "name": "Valid login → navigates to home (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "com.example.myapp", "description": "Cold start: terminateApp then launchApp"},
            {"action": "wait", "value": "3000", "description": "Wait for app startup, first-frame render takes 2-3s"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "pass1234", "description": "Enter password (replace with actual test data)"},
            {"action": "click", "target": "accessibility_id:btn_login", "description": "Tap login button (replace selector with actual accessibilityIdentifier)"},
            {"action": "wait", "value": "3000", "description": "Wait for API response and screen transition"},
            {"action": "assert_text", "expected": "Welcome", "description": "Verify home screen text (replace with actual text from source code)"},
            {"action": "screenshot", "description": "Home screen after login"}
          ]
        },
        {
          "name": "Invalid login → error shown (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "com.example.myapp", "description": "Flow mode: navigate auto-skipped, already on login screen"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "wrong", "description": "Enter wrong password"},
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
- [ ] All interactive elements have `.accessibilityIdentifier()` in Swift code
- [ ] `bundle_id` confirmed from Xcode project settings
- [ ] `base_url` is `""`
- [ ] All selectors use `accessibility_id:xxx` format
- [ ] `expected` text comes from persistent Text/Label widgets (not alerts/toasts)

### MANDATORY Post-Generation Checks (3 required  fix if any fail)

**Check 1  Flow decision:** For each page with 2 scenarios that ALL require login first:
- YES  that page MUST have `"flow": true` AND non-first scenarios MUST NOT contain login steps
- NO  no flow needed (each scenario independently cold-starts)

**Check 2  Assert coverage:** For every scenario, does it have at least one `assert_text` step?
- Screenshot alone is NOT sufficient  must have text assertion
- `expected` must be text permanently visible in a Text/Label widget (not .alert() auto-dismiss)

**Check 3  Duplicate login check:** Are there 3 scenarios with identical login step sequences?
- YES  merge those scenarios into one page with `"flow": true`, login only once in first scenario

---

## TEN: Gotcha Table

| Mistake | Consequence | Correct Approach |
|---------|-------------|-----------------|
| No `.accessibilityIdentifier()` in Swift | Element not found | Add modifier to every interactive element |
| CSS selector `#id` | XCUITest doesn't support it | Use `accessibility_id:xxx` |
| Android `id:xxx` format | XCUITest doesn't support it | Use `accessibility_id:xxx` |
| No wait after navigate | Elements not yet rendered | Always `wait 3000` after cold start |
| `.sheet()` without wait 800 | Animation incomplete, elements inside not ready | Add `wait 800` after trigger |
| `base_url` set to bundle_id | Engine confused | `base_url` must be `""` |
| Asserting `.alert()` text | Alert may already be dismissed | Assert persistent Text/Label widgets |

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
- Validated by: device screen resolution + `bundle_id`
- If device or bundle ID changes: old cache is discarded automatically
- Cache file location: `testpilot/.page_cache.json` (auto-created next to the blueprint file)

**What this means for blueprints:**
- You do NOT need special steps to "enable" or "update" the cache — it is fully automatic
- First test run is slower (AI analysis per new page); subsequent runs are faster (cache reuse)
- The cache persists across multiple test runs and across ALL blueprint files in the same `testpilot/` directory
- To force a full re-analysis (e.g. after major UI redesign): delete `testpilot/.page_cache.json`
- **Do not gitignore `.page_cache.json`** — keeping it in source control lets teammates reuse the same coordinates without re-running AI analysis
