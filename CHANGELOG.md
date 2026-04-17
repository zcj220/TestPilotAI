# Changelog

All notable changes to TestPilot AI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🎯 Planned
- iOS testing support (Appium + WebDriverAgent)
- macOS desktop testing
- Input fault tolerance mechanism
- Cloud deployment option
- Team collaboration features

---

## [1.2.1] - 2026-03-11

### ✨ Added
- Blueprint memo system (`testpilot/CHANGELOG.md`) for AI handoff
- Absolute positive verification in blueprint prompts
- Exhaustive input variant testing (case variations, etc.)

### 🐛 Fixed
- Android Y-key bug (keyboard not closed before click)
- Android S-key bug (keyboard animation timing)
- `xpath:` prefix not recognized in selectors
- `assert_text` returning accessibility_id instead of actual text
- Invalid selector error handling (now falls back to visual AI)

### 📚 Documentation
- Enhanced blueprint generation guidelines
- Added "code is the only truth" principle
- Improved blueprint self-check checklist

---

## [1.2.0] - 2026-03-10

### ✨ Added
- Native Android testing support (95% pass rate)
- Flutter Android testing support (95% pass rate)
- Pure ADB input method (no Appium dependency for input)
- UI Tree + AI Visual dual insurance system
- Automatic Latin IME switching for Android
- Visual element search with auto-scroll

### 🐛 Fixed
- Android keyboard input reliability issues
- Flutter element location failures
- Input method switching on password fields
- XPath selector parsing errors

### 📚 Documentation
- Added Android testing guide
- Updated platform support table
- Added troubleshooting section for mobile testing

---

## [1.1.0] - 2026-03-08

### ✨ Added
- Mobile blueprint runner for Android/iOS
- Appium integration for mobile automation
- AI visual analysis for mobile UI
- Mobile session management API

### 🔧 Changed
- Refactored blueprint runner for multi-platform support
- Improved AI prompt system for mobile testing

---

## [1.0.0] - 2026-03-01

### 🎉 Initial Release

#### Core Features
- Blueprint-driven testing for Web, Mobile, Desktop
- Multimodal AI visual analysis (Doubao/OpenAI compatible)
- Auto-repair loop (fix-test-fix cycle)
- Memory system with SQLite storage
- Real-time WebSocket logging
- VSCode/Windsurf extension
- Desktop app (React + Tauri, pending packaging)

#### Platform Support
- ✅ Web apps (Playwright + Docker sandbox)
- ✅ WeChat Mini Programs (Playwright + DevTools)
- 🔄 Windows Desktop (pywinauto + AI visual, 97% pass rate)
- 📋 Android/iOS (planned)

#### API Endpoints
- `/api/v1/test/run` - Run blueprint test
- `/api/v1/test/quick` - Quick exploratory test
- `/api/v1/memory/*` - Memory system APIs
- `/api/v1/community/*` - Community experience sharing

#### Developer Tools
- 166 unit tests with pytest
- FastAPI with auto-generated OpenAPI docs
- Poetry for dependency management
- Docker support for web testing sandbox

---

## [0.7.0] - 2026-02-20

### ✨ Added
- Real-time log streaming via WebSocket
- VNC/screenshot streaming for live monitoring
- Credit metering system for AI API usage
- User authentication and API key management

---

## [0.6.0] - 2026-02-15

### ✨ Added
- Desktop app frontend (React + TailwindCSS + Vite)
- Real-time test monitoring UI
- Test history browsing
- Settings management page

---

## [0.5.0] - 2026-02-10

### ✨ Added
- VSCode/Windsurf extension
- Sidebar webview panel
- Command palette integration
- Right-click context menu
- WebSocket real-time communication

---

## [0.4.0] - 2026-02-05

### ✨ Added
- Auto-repair loop system
- Bug classification AI
- Code patch generation and application
- Patch rollback mechanism
- Fix-test-fix orchestrator

---

## [0.3.0] - 2026-02-01

### ✨ Added
- Cross-validation engine (multi-round AI analysis)
- SQLite memory system
- Test history storage
- Experience accumulation
- Page fingerprinting

---

## [0.2.0] - 2026-01-25

### ✨ Added
- AI test script generation
- Screenshot visual analysis
- Bug detection and reporting
- Test report generation (Markdown)
- Playwright browser automation

---

## [0.1.0] - 2026-01-20

### 🎉 Project Initialization
- FastAPI application skeleton
- Docker sandbox management
- Basic API endpoints
- Configuration system (pydantic-settings)
- Logging system (loguru)

---

## Legend

- 🎉 Major release
- ✨ New features
- 🐛 Bug fixes
- 🔧 Changes
- 📚 Documentation
- 🔒 Security
- ⚠️ Deprecated
- 🗑️ Removed
