<!-- TestPilot-Template-Version: 10 -->
# Platform Blueprint Rules (platform = "miniprogram")

> This file defines all rules for WeChat Mini Program blueprints.
> AI coding assistants MUST read this file completely before generating any blueprint content.

---

## ZERO: Read Source Code First (Mandatory Pre-Step)

**Before writing any blueprint, follow these steps in order:**

1. Read ALL WXML files to find actual element classes and placeholder attributes
2. Read ALL JS/TS page files to find navigation paths, bindtap handlers, data bindings
3. Read ALL API call code to estimate actual async delay times
4. Confirm the absolute project path for `base_url` (e.g. `"miniprogram://D:/Projects/my-mini"`)
5. Read ALL page.json and app.json to understand page routes

**Why this matters:** WXML is NOT HTML. `#id` selectors, `:contains()`, `div`/`span` tags  none of these work in Mini Programs.

---

## ONE: Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | YES | Must be `"miniprogram"` |
| `base_url` | YES | `"miniprogram://absolute-path"` e.g. `"miniprogram://D:/Projects/my-mini"` |
| `app_name` | YES | Display name |
| `description` | YES | 50-200 chars: what the mini program does and what scenarios are covered |

**Note:** Engine automatically handles environment setup (cli close  cli open  cli auto --auto-port 9420). Do NOT write restart steps in the blueprint.

---

## TWO: Available Actions

### Standard Actions

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `value` (page path) | Navigate to a mini program page path e.g. `"pages/login/login"` |
| `click` | `target` (CSS-like selector) | Tap an element |
| `fill` | `target`, `value` | Clear and type text into an input field |
| `select` | `target`, `value` | Select value from a `<picker>` component |
| `wait` | `value` (ms) | Fixed wait in milliseconds |
| `assert_text` | `expected` | Assert page contains this text |
| `screenshot` |  | Take a screenshot |

### Mini Program-Specific Actions

| Action | Description |
|--------|-------------|
| `navigate_to` | Navigate using `wx.navigateTo` programmatically |
| `evaluate` | Execute JavaScript in the page context |
| `page_query` | Query page data/state |
| `call_method` | Call a page method directly |
| `read_text` | Read text from an element |
| `tap_multiple` | Tap multiple elements in sequence |
| `scroll` | Scroll within a scroll-view |
| `assert_compare` | Compare values with operators |

**Forbidden for miniprogram:** `reset_state`

---

## THREE: Selector Rules

### WXML is NOT HTML  Critical Differences

| HTML concept | WXML equivalent | Selector rule |
|---|---|---|
| `<div>` | `<view>` | Use `view.classname`, NOT `div` |
| `<span>` | `<text>` | Use `text.classname`, NOT `span` |
| `id="xxx"` attribute | Same syntax but... | `#xxx` does NOT work in automator |
| `:contains("text")` |  | NOT SUPPORTED  causes errors |
| `input[type="text"]` | `<input>` has no `type` attribute | Use `input[placeholder*='xxx']` |

### Correct Selectors (by priority)

| Priority | Format | Example | When to use |
|----------|--------|---------|------------|
| 1 | `input[placeholder*='xxx']` | `input[placeholder*='Username']` | Distinguish input fields |
| 2 | `button.class-name` | `button.btn-primary` | Confirm bindtap targets the right button |
| 3 | `.parent .child` | `.card .form-input` | Narrow scope with parent container |
| 4 | `view[data-tab='xxx']` | `view[data-tab='profit']` | Mini programs often use data-xxx for state |
| 5 | Text description | In `description` field | Describe element text to help engine locate it |

### picker Component: Use select Not click

```json
CORRECT: {"action": "select", "target": "picker.type-picker", "value": "Income"}
WRONG:   {"action": "click", "target": "picker.type-picker"}
```
`<picker>` is a native component  it cannot be clicked like a button.

### TabBar Navigation: Use navigate Not click

```json
CORRECT: {"action": "navigate", "value": "pages/reports/reports"}
WRONG:   {"action": "click", "target": ".tab-bar-item"}
```
Native TabBar is NOT in the WXML DOM  cannot be selected.

---

## FOUR: Transient UI  Cannot Be Asserted

| Component | Why it cannot be asserted |
|-----------|--------------------------|
| `wx.showToast()` | Auto-disappears; not in WXML DOM |
| `wx.showModal()` | **Native popup  NOT in WXML DOM**  automator cannot interact |
| `wx.showLoading()` | Loading overlay, transient |
| `wx.showActionSheet()` | Native action sheet, not in DOM |

**CANNOT click "confirm" / "cancel" on `wx.showModal()`**  
If your business logic depends on modal confirmation, advise the developer to use a custom in-page dialog component instead.

**Persistence validation guide:**
```
CAN assert:
  <text class="title">Record Book</text>     expected: "Record Book"
  <view class="amount">100</view>           expected: "100"
  Any WXML element that persists on screen

CANNOT assert:
  wx.showToast({ title: 'Saved' })           transient, disappears before assertion
  wx.showModal({ title: 'Confirm Delete' })  native popup, not in DOM
```

---

## FIVE: Wait Time Formula

```
wait = async_delay_in_code + 1500ms  (buffer for Mini Program render + Automator refresh)
```

| Scenario | Recommended wait |
|----------|-----------------|
| `wx.request()` API call + data render | API_time + 1500 |
| `wx.navigateTo()` page transition | wait 1500 |
| `wx.reLaunch()` page reload | wait 2000 |
| `setData()` local data update only | wait 1000 |
| `<picker>` selection  data update | wait 1000 |

---

## SIX: Scenario Isolation Principle and Flow Mode

### Mandatory Flow Decision for Every Page

**Check these rules in order when generating scenarios for each `page`:**

1. Does this page have 2 scenarios that ALL require login first?  **MUST set `"flow": true`**
2. Does this page have 2 scenarios that are TabBar switches or continuous operations?  **MUST set `"flow": true`**
3. Do scenarios need independent clean state (e.g. correct login vs wrong login)?  No flow (default `false`)

### Default Mode (flow: false)

- Engine automatically calls `wx.reLaunch` before each scenario to reset page stack
- Engine handles all DevTools CLI steps: cli close  cli open  cli auto --auto-port 9420
- Each scenario MUST start with `navigate` to its starting page path
- **Do NOT** write DevTools restart steps in the blueprint  engine handles it
- **FORBIDDEN** to share state between scenarios

### Flow Mode (flow: true)

Set `"flow": true` at the `page` level. Scenarios run sequentially:
- Only the 1st scenario's `navigate` actually navigates; subsequent `navigate` steps are auto-skipped
- Page state preserved between scenarios
- If 3 consecutive scenarios fail  engine calls reLaunch to recover, then continues
- Each scenario must still include `navigate` (for independent running)

### CRITICAL: Non-First Scenario Rules in Flow Mode

**In flow mode, scenarios #2, #3, etc. must ONLY have: navigate + that scenario's own operations. NEVER repeat login steps.**

If step 2 of a non-first scenario is `fill username`, but the page is already on the main tab (logged in from scenario 1), the input is NOT FOUND  timeout  3 consecutive failures  scenario aborted  chain of failures.

| WRONG | CORRECT |
|-------|---------|
| navigate  fill username  fill password  click login  wait  actual ops | navigate  actual ops  assert_text |

**Rule: In flow mode, only the FIRST scenario does the complete navigate + login. All others start directly with their own operations.**

---

## SEVEN: Setup — Reusable Navigation Paths

When 3+ scenarios share the same prefix steps (e.g. navigate to page → login → enter module), extract them into `setups`.

- Define each navigation path once in `"setups"` at the top level
- Reference it via `"setup": "name"` in each scenario
- Use `"extends": "parent_name"` to chain paths (e.g. `enter_settings` extends `login`)
- The engine resolves the full chain and prepends all steps before the scenario’s own steps
- Max 3 levels of extends; no circular references

---

## EIGHT: Complete JSON Template

```json
{
  "app_name": "Your Mini Program Name",
  "description": "50-200 char description of features and test coverage",
  "base_url": "miniprogram://D:/Projects/your-mini-program",
  "platform": "miniprogram",
  "setups": {},
  "pages": [
    {
      "url": "pages/index/index",
      "name": "Home Page",
      "flow": true,
      "scenarios": [
        {
          "name": "Valid login → redirects to home (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "pages/login/login", "description": "Open login page"},
            {"action": "fill", "target": "input[placeholder*='Username']", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "input[placeholder*='Password']", "value": "pass1234", "description": "Enter password (replace with actual test data)"},
            {"action": "click", "target": "button.btn-primary", "description": "Click login button (replace selector with actual class from WXML)"},
            {"action": "wait", "value": "2000", "description": "Wait for API verification and page redirect"},
            {"action": "assert_text", "expected": "Home Page", "description": "Verify redirect success (replace with actual page title from source)"},
            {"action": "screenshot", "description": "Home page after login"}
          ]
        },
        {
          "name": "Add new item via form (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "pages/index/index", "description": "Flow mode: navigate auto-skipped, already on home page"},
            {"action": "click", "target": "button.add-btn", "description": "Click add button (replace selector with actual class)"},
            {"action": "wait", "value": "1000", "description": "Wait for form to load"},
            {"action": "select", "target": "picker.type-picker", "description": "Select option from picker (replace selector and value)"},
            {"action": "fill", "target": "input[placeholder*='Amount']", "value": "100", "description": "Enter value (replace with actual test data)"},
            {"action": "click", "target": "button.save-btn", "description": "Click save button (replace selector with actual class)"},
            {"action": "wait", "value": "1500", "description": "Wait for save and list refresh"},
            {"action": "assert_text", "expected": "100", "description": "Verify item appears (replace with actual expected text)"},
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
- [ ] Read ALL WXML files, confirmed class names and placeholder text
- [ ] No `#id` selectors used anywhere
- [ ] No `:contains()` pseudo-class used
- [ ] `<picker>` uses `select` action, not `click`
- [ ] TabBar navigation uses `navigate` with page path, not `click`
- [ ] `base_url` is `"miniprogram://absolute-path"` (absolute path, not relative)
- [ ] `expected` text comes from persistent WXML elements (not wx.showToast/wx.showModal)

### MANDATORY Post-Generation Checks (3 required  fix if any fail)

**Check 1  Flow decision:** For each page with 2 scenarios that ALL require login first:
- YES  that page MUST have `"flow": true` AND non-first scenarios MUST NOT contain login steps
- NO  no flow needed (each scenario independently logs in and navigates)

**Check 2  Assert coverage:** For every scenario, does it have at least one `assert_text` step?
- Screenshot alone is NOT sufficient  must have text assertion
- `expected` must come from persistent WXML element text (not wx.showToast/wx.showModal)

**Check 3  Duplicate login check:** Are there 3 scenarios with identical login step sequences?
- YES  merge into one page with `"flow": true`, login only once in first scenario

---

## TEN: Gotcha Table

| Mistake | Consequence | Correct Approach |
|---------|-------------|-----------------|
| Using `#login-btn` selector | WXML doesn't support id selectors | Use `button.btn-primary` or class |
| Using `button:contains('Login')` | `:contains()` not supported in automator | Use class + describe text in description |
| Using `click` on `<picker>` | picker is native component | Use `select` action |
| Clicking `wx.showModal` confirm | Native modal not in DOM | Skip or redesign using custom component |
| Asserting `wx.showToast` text | Transient, may already be gone | Assert persistent state change in WXML |
| `base_url` using relative path | Engine can't find project | Use absolute path: `miniprogram://D:/Projects/app` |
| TabBar navigation via `click` | Native TabBar not in DOM | Use `navigate` with page path |
| Using `div`/`span` tags | WXML has `view`/`text` tags | Use correct WXML tag names |
| Using `input[type="text"]` | WXML `input` has no `type` attribute | Use `input[placeholder*='xxx']` |
| Hardcoded registered username | Fails on second run (user already exists) | Use timestamp username or clear data first |
| Scenario 2 depends on scenario 1 login | Engine resets state before every scenario | Each scenario must independently login |
