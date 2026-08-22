# Anti-Bagu Plain-Language Redesign QA

- Source visual truth: `/Users/yangchaoqun/Proj/Anti-Bagu/docs/assets/product-plain-language-option-2.png`
- Implementation screenshot: `/tmp/anti-bagu-redesign-prep-v2.jpg`
- Side-by-side comparison: `/tmp/anti-bagu-redesign-compare-v2.jpg`
- Mobile viewport screenshot: `/tmp/anti-bagu-redesign-mobile-viewport.jpg`
- Settings screenshot: `/tmp/anti-bagu-redesign-settings.jpg`
- Admin screenshot: `/tmp/anti-bagu-redesign-admin.jpg`
- Production screenshot: `/tmp/anti-bagu-plain-language-production.jpg`
- Final disconnected-state screenshot: `/tmp/anti-bagu-install-prompt-production.jpg`
- Browser URL: `http://127.0.0.1:5174/tasks/5b358595-5559-4eb0-9302-452c0729aa5b`
- Production URL: `https://101.42.92.125/tasks/d2857a52-fa47-412f-942f-1fa0aa903cb1`
- State: newly created interview, preparation step 1 active, computer helper not connected
- Source pixels: 1487 × 1058
- Implementation pixels: 1440 × 1024
- CSS viewport: 1440 × 1024
- Density normalization: source scaled to 1440 × 1024 before horizontal comparison

## Full-view comparison evidence

The implementation preserves the selected direction's compact interview-history sidebar, centered preparation heading, three-step progression, circular Phosphor-style icons, single blue primary action, optional phone row, generous whitespace, navy typography, and restrained blue/green palette.

The implementation intentionally shows `完成 0 / 3` while the concept image shows `完成 1 / 3` with step 1 still active. Zero is the truthful product state before the computer helper connects. It also adds a small `已经打开，重新连接` recovery action because a downloaded helper may already be installed.

## Focused-region comparison

A separate crop was not required: the normalized 2880 × 1024 side-by-side image keeps the title, progress value, all three step labels, primary action, phone prompt, sidebar states, typography and spacing readable. The full page contains no photographic or custom raster assets; all visible UI symbols use the existing Phosphor icon library.

## Required fidelity surfaces

- Typography: heading scale, weight, line height and centered hierarchy closely match the selected source.
- Spacing and layout: the three equal steps, connecting rhythm, sidebar width, phone divider and action spacing match the source composition.
- Colors and tokens: existing white, navy, blue, muted gray and green product tokens remain consistent with the source.
- Image and icon quality: no placeholder imagery, emoji, custom SVG or CSS-drawn asset is used; icons come from one library.
- Copy and content: ordinary user pages contain no Agent, Focus, ASR, LLM, Worker, Runtime, Keychain, WSS, model ID, sample-rate or storage-path terminology.

## Interaction evidence

- Created a new interview and reached the first preparation step.
- Download action is present and the secondary reconnect action triggers a real preflight request.
- Failed reconnection returns plain recovery copy: `电脑助手还没有连接`.
- Account control now opens a menu before logout instead of logging out immediately.
- `/models` redirects to the unified plain-language settings page.
- Login, create, live, reviews, settings and all five admin routes were scanned for prohibited technical vocabulary; no matches remained.
- Desktop routes measured no horizontal overflow at 1440px.
- The preparation route measured `scrollWidth === innerWidth` at 390px.
- Browser warning/error logs were empty.
- The deployed HTTPS page was recaptured after release; the three-step flow rendered correctly with no console warnings or errors.

## Comparison history

### Iteration 1

- Finding P2: the first implementation capture displayed preparation step 2 because it used an existing task with a persisted computer connection result, while the source displayed step 1.
- Resolution: created a clean interview and recaptured the same step-1 state. No visual code change was needed.

### Iteration 2

- Recompared the normalized source and aligned implementation.
- No actionable P0, P1 or P2 differences remain.

### Iteration 3

- User feedback: the disconnected state over-explained installation with a large three-step panel.
- Fix: reduced it to one factual status — `电脑助手未连接` — and two possible causes: not installed, or installed but not opened.
- The two recovery actions are now `尚未安装，立即下载` and `已经安装，重新连接`.
- Production recapture confirms the long guide is gone, both recovery paths are visible, no technical terms leaked, and browser logs remain clean.

## Follow-up polish

- P3: on narrow screens the interview-history section appears before the preparation content. This is usable and has no overflow, but could become a compact collapsible list in a later mobile-specific pass.

final result: passed
