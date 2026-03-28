<!-- TestPilot-Template-Version: 16 -->
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
| 5 | `:has-text('x')` | `button:has-text('Submit')` | Button has visible text but no id/title/semantic class. **Preferred for Tailwind CSS projects** where buttons rarely have semantic classes. Verify text exactly matches source code. |

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
1. Prefer `id`, `name`, `title`, `placeholder`, `data-testid`, `type` attributes — **only if the attribute actually exists in source code** (open the file and verify!)
2. Find a **semantic class** unique to the element (e.g. `.submit-btn`, NOT `.flex`)
3. If only Tailwind classes exist, use context combo: `.parent-class button[title='xxx']`
4. Last resort: ask the developer to add `data-testid` or `id`

**Pitfall 5  Submit button trap:**
Many React/Vue forms do NOT use `<button type="submit">`. They use `<button onClick={handler}>` instead. **Always check source code** before writing `button[type='submit']`.

**Pitfall 6  React/Vue/Angular component names are NOT CSS classes:**
Custom components like `<Select>`, `<Modal>`, `<DatePicker>` do NOT appear as CSS classes in rendered DOM. `div[class*='Select']` will NOT work. Open the component source file and check the actual rendered root element's class.

### Forbidden selectors

- ❌ `div[class*='ComponentName']` — component name ≠ CSS class
- ❌ `svg[class*='IconName']` — icon library rendered class ≠ JSX component name (see Pitfall 14)
- ❌ `button:has(> svg[class*='xxx'])` — SVG class matching is always wrong (see Pitfall 14)
- ❌ `div:nth-child(N)` — fragile, breaks on DOM changes
- ❌ `body > div > div > form > input` — too deep, breaks easily
- ❌ `accessibility_id:xxx` — mobile-only selector, NOT for Web
- ❌ `name:xxx` — desktop-only selector, NOT for Web
- ❌ Bare tag selectors (`div`, `span`, `button` with no attributes)

**Pitfall 12  Bare `button` selector (CRITICAL):**
Writing `"target": "button"` with no attributes is forbidden. Playwright matches the **first** button in the DOM, which may be a hidden button, an icon button, or the wrong button entirely. This is the most common cause of wrong-element clicks that appear to succeed (no error) but operate the wrong control.

| ❌ Forbidden | Why wrong | ✅ Correct approach |
|---|---|---|
| `"target": "button"` | Matches ANY button, usually wrong one | Read source: use `button[type='submit']`, `#btn-register`, `.btn-life-book` etc. |
| `"target": "span"` | Matches ANY span | Use `#id` or semantic class |

> **Iron rule:** Every `click` target MUST have at least one attribute constraint. Bare tag selectors (`button`, `a`, `div`, `span`) are FORBIDDEN without exception.

**Pitfall 13  State-based routing — URL navigation does NOT switch pages (CRITICAL):**
Some React/Vue apps use a store value (Zustand/Redux/Context) to decide which component to render: `if (currentApp === 'business') return <BusinessApp />`. These apps have **no URL router** (`react-router-dom`, Vue Router etc.).

In these apps:
- `navigate("http://localhost:3000/business")` does NOT enter the business module — the store state is cleared loading the URL, so the app shows the login page
- The only way to enter a sub-module is: full login → click the correct UI button
- Every scenario MUST start from the login URL and do the complete login + UI navigation flow
- **ALL pages in such apps MUST be `flow: false`** (each scenario is fully self-contained)

**How to identify state-based routing (check before writing any blueprint):**
1. Search `App.tsx` / `app.vue` for `if (state === 'xxx') return <Component/>` — if found → state-based routing
2. Check `package.json` — if NO `react-router-dom` / `vue-router` / `@angular/router` → state-based routing
3. If URL changes but page stays the same after clicking nav items → state-based routing

### ⚠️ Attribute Selectors Require Source Verification

When using `[title='xxx']`, `[aria-label='xxx']`, `[data-testid='xxx']`, `[placeholder='xxx']`:

1. **MUST open the source file first** and confirm the attribute exists on that element
2. **NEVER guess attribute values** from the element's visible text or purpose
3. `[title]` is a tooltip attribute — many icon buttons in React/Vue apps do NOT have it

> Typical mistake: seeing a "财务报表" navigation button and writing `button[title='财务报表']` — but the button has no `title` attribute in source code → 10s timeout on every run.

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

**Pitfall 14  SVG class selectors are ALWAYS wrong (CRITICAL):**
Selectors like `svg[class*='Plus']`, `button:has(> svg[class*='ArrowLeft'])`, or `svg.icon-name` are FORBIDDEN. Reason:
- React icon libraries (Lucide, Heroicons, react-icons) use JSX component names like `<Plus />`, `<ArrowLeft />` in source code
- But the rendered SVG gets completely different class names: `lucide lucide-plus`, `heroicon-outline`, etc.
- `class*='Plus'` (capital P) will NEVER match `lucide-plus` (lowercase) — CSS attribute selectors are case-sensitive
- Even if you try `class*='plus'`, Lucide renders `class="lucide lucide-plus"` — matching on SVG internals is fragile and breaks between library versions

| ❌ Forbidden selector | Why it fails | ✅ Correct selector |
|---|---|---|
| `svg[class*='Plus']` | Rendered class is `lucide lucide-plus`, not `Plus` | `button:has-text('记一笔')` |
| `button:has(> svg[class*='ArrowLeft'])` | SVG class differs from component name | `button:has-text('返回')` or `button[aria-label='Go back']` |
| `svg.icon-name` | Icon library changes class format between versions | Target the parent `button` by text/id/aria-label |

> **Iron rule:** NEVER use SVG class names as selectors. Always target the *parent interactive element* (button/link) by its text content, `id`, `aria-label`, or semantic class.

**Pitfall 15  Icon buttons with visible text — use `:has-text()` (CRITICAL):**
When a button contains BOTH an icon AND text, like:
```jsx
<button><Plus className="w-5 h-5" /><span>记一笔</span></button>
```
The correct selector is `button:has-text('记一笔')` — NOT any selector targeting the icon's SVG.

Selector decision tree for icon buttons:
1. Button has `id` or `data-testid`? → Use `#id` or `[data-testid='xxx']`
2. Button has unique semantic class? → Use `.class-name`
3. Button has visible text? → Use `button:has-text('visible text')`
4. Button has `aria-label`? → Use `button[aria-label='xxx']`
5. Button is icon-only with no text/id/class/aria-label? → Ask developer to add `data-testid`

> In Tailwind CSS projects, almost every button lacks semantic classes. Jump directly to step 3 (`button:has-text()`) for buttons with visible text.

**Pitfall 16  `assert_text` expected value MUST come from source code (CRITICAL):**
The `expected` text in `assert_text` must be **copy-pasted from the actual component source file**, not guessed from feature names or page titles.

Common mistake pattern:
- Developer names a feature "财务报表" in the project plan
- AI writes `"expected": "财务报表"` in the blueprint
- But the actual component renders `"财务记录"` — assertion fails every run

**Mandatory verification process:**
1. Identify which component renders the target page (e.g., `BusinessApp.tsx`)
2. Open that file, search for the exact text string you want to assert
3. Copy-paste the exact string (including punctuation, spaces, parentheses)
4. If the text is dynamic (e.g., `财务记录(${count})`), assert only the static part: `"expected": "财务记录"`

> **Iron rule:** Every `assert_text` expected value must have a traceable source file and line number. If you cannot find the text in any source file, do NOT write that assertion.

**Pitfall 17 — `cn()`/`clsx()`/`classnames()` conditional class makes `class*=` selectors unreliable (CRITICAL):**
Modern React/Vue projects use `cn()` (from `tailwind-merge`), `clsx()`, or `classnames()` to conditionally toggle classes:
```jsx
<button className={cn(
  'rounded-full p-3',
  showFab ? 'bg-slate-600' : 'bg-blue-600'  // class changes based on state!
)}>
```
If you write `button[class*='bg-blue-600']`, it works when `showFab=false` but FAILS when `showFab=true` because the class switches to `bg-slate-600`.

**Detection method:** Search the source file for `cn(`, `clsx(`, `classnames(` — if the class you want to use appears inside a ternary (`? :`) or logical (`&&`), it is a **conditional class** and MUST NOT be used in selectors.

| ❌ Forbidden | Why it fails | ✅ Correct approach |
|---|---|---|
| `button[class*='bg-blue-600']` | `cn()` toggles it to `bg-slate-600` | Use `button[title='xxx']`, `#id`, or `:has-text('xxx')` |
| `div[class*='border-blue-500']` | Conditional: `selected ? 'border-blue-500' : 'border-transparent'` | Use `[data-testid]`, `[aria-label]`, or stable non-conditional class |

> **Iron rule:** Any class inside a `cn()` / `clsx()` / `classnames()` ternary expression is FORBIDDEN as a selector. Use `title`, `id`, `aria-label`, `data-testid`, or `:has-text()` instead.

**Pitfall 18 — Cross-component selector uniqueness: same class on 10+ elements (CRITICAL):**
The 3-step validation says "uniqueness check" but many AI assistants only check the current file. Common Tailwind utility classes like `text-slate-300`, `p-2`, `rounded-lg` appear across MANY components. If your selector matches multiple elements, Playwright clicks the **first one in DOM order** — which may be a completely different button hidden behind a modal overlay.

**Mandatory cross-file check process:**
1. After writing a selector, search the **entire project** (not just current file) for that class/attribute
2. If 3+ elements match → the selector is NOT unique enough → add more constraints
3. Constraint strategies: add parent scope (`div.modal button.p-2`), combine multiple classes (`button.p-2.specific-class`), or use a different attribute entirely

| ❌ Dangerous | How many matches | ✅ Safe alternative |
|---|---|---|
| `button[class*='text-slate-300']` | 10+ buttons across different components | `button.p-2[class*='text-slate-300']` (combine with size class to narrow) |
| `button.p-2.rounded-lg` | 5+ close buttons in different modals | `div[class*='bg-black'] button.p-2` (scope to specific overlay) |
| `[class*='flex']` | 100+ elements | Never use layout utility classes as selectors |

> **Iron rule:** After writing any class-based selector, grep the entire project. If 3+ elements match, add specificity constraints or switch to a unique attribute.

**Pitfall 19 — z-index overlay blocking: scope selectors to the topmost layer (CRITICAL):**
When a modal/overlay/drawer is open (typically `position: fixed` + `z-index: 50` + `bg-black/50` backdrop), elements BEHIND the overlay exist in the DOM but CANNOT be clicked — Playwright times out because the overlay intercepts the click.

Common failure pattern:
1. A report page opens as a `fixed inset-0 z-50` overlay
2. Blueprint says `click button.p-2` (return button)
3. Playwright finds a `button.p-2` in the BASE page (behind the overlay) — it's first in DOM order
4. Click fails because the overlay blocks it → 10s timeout → scenario fails

**Rule:** When operating inside a modal/overlay/drawer, ALL selectors in that context MUST be scoped to the overlay container:

| Context | Scope selector pattern |
|---------|----------------------|
| Modal with dark backdrop | `div[class*='bg-black'] button.xxx` |
| Fixed overlay panel | `div[class*='fixed'][class*='z-50'] button.xxx` |
| Slide-out drawer | `div[class*='translate-x'] .content-class` |

**Detection:** If the component JSX has `fixed inset-0` or `z-50` or `bg-black/50` in its outer wrapper, ALL child element selectors must include that wrapper as parent scope.

> **Iron rule:** When a UI layer has `position: fixed` + `z-index`, NEVER use a bare selector for elements inside it. Always prefix with the layer's container selector.

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

**Step 0 — Identify routing type first (MANDATORY before any flow decision):**

- **State-based routing** (Zustand/Redux/Context controls rendering, no `react-router-dom`): **ALL pages MUST be `flow: false`**. URL navigation does not switch pages. Every scenario does the full login → UI click flow independently. STOP — do not apply steps 1-3 below.
- **URL-based routing** (uses `react-router-dom`, Vue Router, etc.): continue to step 1.

**Then check in order:**

1. Does this page have 2+ scenarios where scenario 2/3 truly continues in the same UI state left by scenario 1 (not just "both need login")?  **MUST set `"flow": true`**, put login only in scenario 1.
2. Does this page have sequential tab-switching or chained operations (e.g., fill form → verify → edit → delete)?  **MUST set `"flow": true`**.
3. Do scenarios need independent clean state (e.g. correct login vs wrong login)?  No flow (default `false`).

**Summary:** `flow: true` is for scenarios that are **genuinely sequential** (scenario 2 picks up where scenario 1 ended). It is NOT triggered merely because multiple scenarios all start with login.

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

## EIGHT: Setup — Reusable Navigation Paths

When 3+ scenarios share the same prefix steps (e.g. login → select module), extract them into `setups`.

### When to use setup

| Condition | Action |
|-----------|--------|
| 3+ scenarios start with identical login steps | Extract login steps into a `"login"` setup |
| 2+ scenarios need login + navigate to same module | Create a setup that `extends` the login setup |
| Only 1 scenario uses a path | Do NOT create a setup — inline the steps |

### How it works

```json
{
  "setups": {
    "login": {
      "description": "Login with test account",
      "steps": [
        {"action": "navigate", "value": "http://localhost:3000/login"},
        {"action": "fill", "target": "#username", "value": "testuser"},
        {"action": "fill", "target": "#password", "value": "pass1234"},
        {"action": "click", "target": "#login-btn"},
        {"action": "wait", "value": "2000"}
      ]
    },
    "enter_dashboard": {
      "description": "Login and navigate to dashboard",
      "extends": "login",
      "steps": [
        {"action": "click", "target": "#nav-dashboard"},
        {"action": "wait", "value": "1500"},
        {"action": "assert_text", "expected": "Dashboard"}
      ]
    }
  },
  "pages": [{
    "scenarios": [{
      "name": "Dashboard — view chart",
      "setup": "enter_dashboard",
      "steps": [
        {"action": "click", "target": "#chart-tab"},
        {"action": "assert_text", "expected": "Revenue Chart"}
      ]
    }]
  }]
}
```

The engine resolves the chain: `enter_dashboard` extends `login` → executes login steps first → then enter_dashboard steps → then scenario's own steps.

### Rules

1. **Define once, reference many** — setup steps are written once, all `"setup": "name"` scenarios reuse them
2. **`extends` chains** — a setup can extend another setup (max 3 levels deep to keep it simple)
3. **No circular references** — `A extends B extends A` is invalid (engine will reject it)
4. **setup + flow interaction** — in flow mode, setup steps are included in scenario 1 but skipped (along with navigate) in subsequent scenarios
5. **Each setup MUST end with a verification step** (`assert_text` or `screenshot`) to confirm the path succeeded

---

## NINE: Complete JSON Template

```json
{
  "app_name": "Your App Name",
  "description": "50-200 char description of features and test coverage",
  "base_url": "http://localhost:3000",
  "platform": "web",
  "start_command": "npm start",
  "start_cwd": "D:/Projects/your-app",
  "setups": {},
  "pages": [
    {
      "url": "/login",
      "name": "Login Page",
      "flow": true,
      "scenarios": [
        {
          "name": "Valid login → redirects to home (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "http://localhost:3000/login", "description": "Open login page"},
            {"action": "fill", "target": "#username", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "#password", "value": "pass1234", "description": "Enter password (replace with actual test data)"},
            {"action": "click", "target": "#login-btn", "description": "Click login button (replace selector with actual id/class from source code)"},
            {"action": "wait", "value": "2000", "description": "Wait for API response and page redirect"},
            {"action": "assert_text", "expected": "Welcome", "description": "Verify redirect success (replace expected with actual text from source code)"},
            {"action": "screenshot", "description": "Home page after login"}
          ]
        },
        {
          "name": "Invalid login → error shown (replace with actual scenario)",
          "steps": [
            {"action": "navigate", "value": "http://localhost:3000/login", "description": "Open login page"},
            {"action": "fill", "target": "#username", "value": "testuser", "description": "Enter username (replace with actual test data)"},
            {"action": "fill", "target": "#password", "value": "wrong", "description": "Enter wrong password"},
            {"action": "click", "target": "#login-btn", "description": "Click login button"},
            {"action": "wait", "value": "1500", "description": "Wait for error response"},
            {"action": "assert_text", "expected": "Error", "description": "Verify error message (replace expected with actual error text from source code)"},
            {"action": "screenshot", "description": "Login error state"}
          ]
        }
      ]
    }
  ]
}
```

---

## TEN: Checklist

### Pre-Generation Checklist
- [ ] Read ALL template/component files, confirmed real element IDs/classes
- [ ] Read ALL route files, confirmed actual page paths
- [ ] Read ALL validation logic, confirmed error message exact text
- [ ] Checked `package.json` start script, confirmed `start_command` and port
- [ ] `start_cwd` is an absolute path (e.g. `"D:/Projects/app"`, NOT `"."`) 
- [ ] If 3+ scenarios share login steps, extracted them into `setups`

### MANDATORY Post-Generation Checks (3 required  fix if any fail)

**Check 1  Flow decision (two-step):**
- **Step A — Is this a state-based routing app?** (App.tsx uses `if (state==='x') return <Comp/>`, no `react-router-dom`) → If YES: ALL pages MUST be `flow: false`. Stop here.
- **Step B — For URL-router apps:** Are scenario 2+ truly continuing from the same UI state where scenario 1 ended? → YES: that page MUST have `"flow": true`, and non-first scenarios MUST NOT contain login steps. SCAN every non-first scenario in flow pages: if it contains `fill username` / `fill password` / `click login`, DELETE those steps immediately.

**Check 2  Assert coverage:** For every scenario, does it have at least one `assert_text` step?
- Screenshot alone is NOT sufficient  must have text assertion
- `expected` must be text that is permanently in the DOM, NOT from toast/alert

**Check 3  Duplicate login check:** Are there 3+ scenarios with identical login step sequences?
- YES  merge those scenarios into one page with `"flow": true`, login only once in first scenario

**Check 4  Selector safety scan:** For every `target` in the blueprint:
- Contains `class*=` inside a `cn()`/`clsx()` ternary? → Replace with stable attribute (Pitfall 17)
- Grep the project: does this selector match 3+ elements? → Add specificity (Pitfall 18)
- Element is inside a `fixed z-50` overlay/modal? → Add overlay scope prefix (Pitfall 19)

---

## ELEVEN: Gotcha Table

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
| State-based routing app + `"flow": true` | Scenario 2 runs inside app from scenario 1 (wrong sub-module), element not found → 3× timeout chain | Detect routing type first: no `react-router-dom` in `package.json` → state-based → ALL pages `flow: false` |
| `button:has-text('xxx')` used when button has a stable id/class | Fragile if text changes | Always prefer `#id` or unique `.class`; `:has-text()` is last resort only |
| `svg[class*='IconName']` or `button:has(> svg[class*='xxx'])` | Icon library renders different class names than JSX component; case-sensitive mismatch | Use `button:has-text('text')` or `#id` — NEVER target SVG class |
| `assert_text` expected guessed from feature name | Actual rendered text differs from feature name | Open source file, copy-paste the exact rendered text |
| `button[class*='bg-blue-600']` on `cn()` toggled class | Class switches to `bg-slate-600` at runtime, selector fails | Check for `cn()`/`clsx()` ternary; use `title`, `#id`, or `:has-text()` instead |
| `button.p-2` (class exists on 10+ elements) | Playwright clicks wrong element (first DOM match) | Grep entire project for that class; add parent scope or combine classes |
| Bare selector inside modal/overlay | Matches element behind `z-50` overlay, click blocked | Scope to overlay container: `div[class*='bg-black'] button.xxx` |}
