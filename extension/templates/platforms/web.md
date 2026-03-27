<!-- TestPilot-Template-Version: 15 -->
# Platform Blueprint Rules (platform = "web")

> This file defines all rules for Web application blueprints.
> AI coding assistants MUST read this file completely before generating any blueprint content.

---

## ZERO: Read Source Code First (Mandatory Pre-Step)

**Before writing any blueprint, follow these steps in order:**

1. Read ALL HTML/JSX/TSX/Vue template files to find real element IDs and class names
2. Read ALL route files (App.jsx, router.js, etc.) to confirm actual page paths
3. Read ALL form validation logic to know exact success/error message text
4. Check `package.json` scripts.start to confirm `start_command` and default port
5. Read ALL API call code to estimate actual async delay times

**Why this matters:** Writing selectors from memory without reading source code causes wrong IDs/classes  every test fails from the start.

---

## ONE: Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | YES | Must be `"web"` |
| `base_url` | YES | e.g. `"http://localhost:3000"`  no trailing slash |
| `start_command` | YES | e.g. `"npm start"`, `"python app.py"`  empty for static HTML only |
| `start_cwd` | YES | **MUST be absolute path** e.g. `"D:/Projects/my-app"`  NEVER `"."` |
| `app_name` | YES | Display name |
| `description` | YES | 50-200 chars: what the app does and what scenarios are covered |

### Startup Preconditions Checklist

Before using `start_command`, verify these:
- [ ] Dependencies installed: `npm install` / `pip install -r requirements.txt`
- [ ] Required env vars set (DB URL, API keys, port, etc.)
- [ ] Port not already in use
- [ ] `start_cwd` is absolute path (e.g. `"D:/Projects/my-app"`, NOT `"."`)
- [ ] On Windows, use `/` not `\` in paths

---

## TWO: Available Actions

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `value` (full URL) | Open a URL in the browser |
| `click` | `target` (CSS selector) | Click an element |
| `fill` | `target`, `value` | Clear and type text into an input |
| `select` | `target`, `value` | Choose from a `<select>` dropdown |
| `wait` | `value` (ms) | Fixed wait in milliseconds |
| `assert_text` | `expected` | Assert page contains this text string |
| `screenshot` |  | Take a screenshot |

**Forbidden actions** (not supported): `reset_state`, `navigate_to`, `evaluate`

---

## THREE: Selector Rules

### 3-Step Validation Process

Before writing any selector, do ALL three steps:

1. **Find in source**  open the HTML/JSX/TSX/Vue file, locate the actual element
2. **Copy the attribute**  copy the `id`, `name`, or `class` exactly as written in source
3. **Uniqueness check**  search the codebase to confirm this selector matches only ONE element

### Selector Priority (use in this order)

| Priority | Format | Example | When to use |
|----------|--------|---------|------------|
| 1 | `#id` | `#login-btn` | Element has a unique `id` attribute |
| 2 | `[name="x"]` | `[name="email"]` | Form input with `name` attribute |
| 3 | `.class` | `.submit-btn` | Unique semantic class name |
| 4 | Combination | `form.login-form input[name="pwd"]` | When single attributes are not unique |

### Four Critical Pitfalls

**Pitfall 1  Tailwind CSS atomic classes are INVALID selectors:**
Tailwind generates atomic utility classes like `bg-blue-500`, `text-sm`, `px-4`. These appear on many elements and cannot identify a specific element. You MUST use a semantic `id` or custom class instead.

**Pitfall 2  `button[type="submit"]` may not exist:**
Many React/Vue forms use `<button type="button" onClick={...}>` or `<button>` with no type attribute. Always check the actual HTML source  do NOT assume submit type.

**Pitfall 3  React component names are NOT DOM class names:**
A React component `<LoginForm>` does NOT generate a `.LoginForm` CSS class. Check the rendered DOM output for the actual class names applied.

**Pitfall 4  Tailwind utility classes as selectors:**
Tailwind classes like `.flex`, `.mt-4`, `.bg-blue-600` match dozens of elements. Use semantic attributes (`#id`, `[title]`, `[data-testid]`, `[placeholder]`) instead.

**Tailwind selector strategy:**
1. Prefer `id`, `name`, `title`, `placeholder`, `data-testid`, `type` attributes
2. Find a **semantic class** unique to the element (e.g. `.submit-btn`, NOT `.flex`)
3. If only Tailwind classes exist, use context combo: `.parent-class button[title='xxx']`
4. Last resort: ask the developer to add `data-testid` or `id`

**Pitfall 5  Submit button trap:**
Many React/Vue forms do NOT use `<button type="submit">`. They use `<button onClick={handler}>` instead. **Always check source code** before writing `button[type='submit']`.

**Pitfall 6  React/Vue/Angular component names are NOT CSS classes:**
Custom components like `<Select>`, `<Modal>`, `<DatePicker>` do NOT appear as CSS classes in rendered DOM. `div[class*='Select']` will NOT work. Open the component source file and check the actual rendered root element's class.

### Forbidden selectors

- ❌ `div[class*='ComponentName']` — component name ≠ CSS class
- ❌ `div:nth-child(N)` — fragile, breaks on DOM changes
- ❌ `body > div > div > form > input` — too deep, breaks easily
- ❌ `accessibility_id:xxx` — mobile-only selector, NOT for Web
- ❌ `name:xxx` — desktop-only selector, NOT for Web
- ❌ Bare tag selectors (`div`, `span`, `button` with no attributes)

**Pitfall 7  `:contains()` causes SyntaxError:**
`:contains()` is jQuery-only syntax. Playwright and modern CSS engines do NOT support it. Any selector with `:contains()` throws `SyntaxError: Failed to execute` and aborts the entire scenario. Use `#id`, `.class`, or `[attribute]` selectors instead.

**Pitfall 8  Tailwind decimal classes cause SyntaxError (CRITICAL):**
Tailwind utility classes with decimals (e.g. `gap-0.5`, `translate-y-0.5`, `space-x-2.5`, `inset-0.5`) contain `.5` which Playwright's CSS parser treats as invalid syntax, throwing `SyntaxError: Unexpected token ".5"` and aborting the entire scenario.

| ❌ Forbidden (SyntaxError) | ✅ Alternative |
|---|---|
| `div.gap-0.5` | Find the element's `id`, semantic class, or `title` attribute |
| `div.translate-y-0.5` | Use parent/child stable semantic attributes |

> **Iron rule:** Tailwind classes containing a decimal point (`0.5`, `1.5`, `2.5`) must NEVER appear in `target`.

**Pitfall 9  Do not guess child element HTML tags:**
Before writing `> div:first-child` or `> li:last-child`, open source code to verify the actual child tag. A flex parent's children might be `button`, `a`, or `li` — not necessarily `div`.
**Pitfall 10  Multiple buttons in a form — use precise selectors:**
When a `<form>` has both utility buttons (e.g. password toggle `type="button"`) and a submit button, `form button` is ambiguous. Playwright clicks the first match which may be the wrong button.

**Pitfall 11  React icon library class names differ from component names:**
Icon libraries (Lucide, Heroicons, react-icons) render SVG with different class names than the component name. `<ArrowLeft />` does NOT render with class `ArrowLeft`. Target the wrapping button instead of the SVG.

> Note: `title="xxx"` is a tooltip attribute, NOT visible page text. Do NOT use `assert_text` on it — use `assert_visible` instead.

---

## FOUR: Transient UI  Cannot Be Asserted

| Component | Why it cannot be asserted |
|-----------|--------------------------|
| Browser `alert()` / `confirm()` | Native dialog, not in DOM |
| Toast / notification popup | Disappears after 2-3 seconds |
| CSS transition message | Gone before assertion runs |

**Rule:** Only assert text that is permanently rendered in the DOM. If you see `wx.showToast` or `setTimeout(() => setMessage(''), 2000)` in the source code, that text CANNOT be used in `assert_text`.

---

## FIVE: Wait Time Formula

```
wait = async_delay_in_code + 1500ms  (buffer for browser render + WebDriver refresh)
```

| Scenario | Recommended wait |
|----------|-----------------|
| API call + page re-render | API_time + 1500 |
| Page navigation (SPA route change) | 1500 |
| Form submit + redirect | 2000 |
| Purely local state update (no API) | 800 |
| File upload | upload_time + 2000 |

---

## SIX: Scenario Isolation Principle and Flow Mode

### Mandatory Flow Decision for Every Page

**Check these rules in order when generating scenarios for each `page`:**

1. Does this page have 2 scenarios that ALL require login first?  **MUST set `"flow": true`**
2. Does this page have 2 scenarios that are sequential tab-switching or continuous operations?  **MUST set `"flow": true`**
3. Do scenarios need independent clean state (e.g. correct login vs wrong login)?  No flow (default `false`)

**Summary:** If multiple scenarios all require login-then-operate on the same page, that page MUST have `"flow": true`. Without flow, every scenario cold-starts and re-logs in = massive waste.

### Default Mode (flow: false)

- Engine clears `localStorage` / `sessionStorage` / `cookie` before each scenario
- Each scenario MUST start with `navigate` to its starting URL
- Scenarios are fully independent  FORBIDDEN to share state between scenarios

### localStorage Pitfall in Flow Mode

If the app checks login state via `localStorage`, the FIRST scenario in a flow page must click "logout" first (if user was already logged in from previous run), THEN log in fresh. Otherwise the first scenario starts already-logged-in and re-login fails.

### Flow Mode (flow: true)

Set `"flow": true` at the `page` level. Scenarios run sequentially within the page:
- Only the 1st scenario's `navigate` actually navigates  subsequent `navigate` steps are auto-skipped
- App state is preserved between scenarios
- If 3 consecutive scenarios fail, engine attempts a cold-start recovery then continues
- Each scenario must still include `navigate` (so it can run independently when needed)

### CRITICAL: Non-First Scenario Rules in Flow Mode

**In flow mode, scenarios #2, #3, etc. must ONLY have: navigate + that scenario's own operations. NEVER repeat login steps.**

The engine skips the `navigate` in non-first scenarios and directly runs step 2 onward. If step 2 is `fill username`, but the page is already on the dashboard (after login from scenario 1), the input field is NOT FOUND  timeout  3 consecutive failures  scenario aborted  all subsequent scenarios fail the same way.

| WRONG (non-first scenario re-logs in) | CORRECT (non-first scenario operates directly) |
|---|---|
| navigate  wait  fill username  fill password  click login  wait  actual operation | navigate  actual operation  assert_text |

**Rule: In flow mode, only the FIRST scenario does the full cold-start + login. All others start directly with their own operation.**

---

## SEVEN: Dialog Isolation Rule

**One scenario = one dialog/form entry point.**

Do NOT put multiple independent dialog interactions in one scenario. Each distinct user flow (open dialog A vs open dialog B vs cancel dialog) should be a separate scenario. This makes failures easier to diagnose and scenarios easier to maintain.

**Exception:** If dialog B can only appear AFTER dialog A completes (they are sequential), they can be in the same scenario or in a flow page.

---

## EIGHT: Complete JSON Template

```json
{
  "app_name": "Your App Name",
  "description": "50-200 char description of features and test coverage",
  "base_url": "http://localhost:3000",
  "platform": "web",
  "start_command": "npm start",
  "start_cwd": "D:/Projects/your-app",
  "pages": [
    {
      "url": "/login",
      "name": "Login Page",
      "flow": true,
      "scenarios": [
        {
          "name": "Correct credentials  login success",
          "steps": [
            {"action": "navigate", "value": "http://localhost:3000/login", "description": "Open login page"},
            {"action": "fill", "target": "#username", "value": "admin", "description": "Enter username in the username field"},
            {"action": "fill", "target": "#password", "value": "admin123", "description": "Enter password in the password field"},
            {"action": "click", "target": "#login-btn", "description": "Click login button, triggers API validation then redirects to dashboard"},
            {"action": "wait", "value": "2000", "description": "Wait for API response and page redirect"},
            {"action": "assert_text", "expected": "Dashboard", "description": "Verify dashboard page loaded successfully"},
            {"action": "screenshot", "description": "Dashboard after login"}
          ]
        },
        {
          "name": "Wrong password  error message shown",
          "steps": [
            {"action": "navigate", "value": "http://localhost:3000/login", "description": "Open login page"},
            {"action": "fill", "target": "#username", "value": "admin", "description": "Enter username"},
            {"action": "fill", "target": "#password", "value": "wrongpass", "description": "Enter wrong password"},
            {"action": "click", "target": "#login-btn", "description": "Click login, API returns 401"},
            {"action": "wait", "value": "1500", "description": "Wait for error response"},
            {"action": "assert_text", "expected": "Invalid credentials", "description": "Verify error message appears permanently in DOM"},
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
- [ ] Read ALL template/component files, confirmed real element IDs/classes
- [ ] Read ALL route files, confirmed actual page paths
- [ ] Read ALL validation logic, confirmed error message exact text
- [ ] Checked `package.json` start script, confirmed `start_command` and port
- [ ] `start_cwd` is an absolute path (e.g. `"D:/Projects/app"`, NOT `"."`)

### MANDATORY Post-Generation Checks (3 required  fix if any fail)

**Check 1  Flow decision:** For each page with 2 scenarios that ALL require login first:
- YES  that page MUST have `"flow": true` AND non-first scenarios MUST NOT contain login steps
- NO  no flow needed (each scenario independently logs in)

**Check 2  Assert coverage:** For every scenario, does it have at least one `assert_text` step?
- Screenshot alone is NOT sufficient  must have text assertion
- `expected` must be text that is permanently in the DOM, NOT from toast/alert

**Check 3  Duplicate login check:** Are there 3+ scenarios with identical login step sequences?
- YES  merge those scenarios into one page with `"flow": true`, login only once in first scenario

---

## TEN: Gotcha Table

| Mistake | Consequence | Correct Approach |
|---------|-------------|-----------------|
| `start_cwd: "."` | Engine can't find project | Use absolute path: `"D:/Projects/app"` |
| Tailwind class as selector | Matches dozens of elements | Use semantic `#id` or custom class |
| `:contains("text")` in selector | SyntaxError crash | Use `#id` or `.class` |
| React component name as class | Element not found | Check rendered DOM for actual class |
| `button[type="submit"]` without checking | Element not found | Check source for actual button type |
| flow non-first scenario has login steps | Input not found, 3-step timeout, scenario abort | Non-first scenario: navigate + own steps only |
| assert_text on toast message | Flaky: passes sometimes, fails sometimes | Assert on permanently rendered DOM text |
| `localStorage` not cleared in flow first scenario | Already logged in, re-login fails | Click logout first, then log in fresh |
| Forgot `navigate` in non-first flow scenario | Can't run scenario independently | Always include navigate (engine auto-skips in flow) |
| Multiple dialogs in one scenario | Hard to diagnose failures | One scenario per dialog/form entry point |
