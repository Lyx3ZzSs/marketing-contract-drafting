# Contract preview — selected direction 3

final result: passed

## Evidence and scope

- Source: `../contract-preview-options/option-3.png` (1487 × 1058).
- Implementation: `normal-preview-light.png` (1395 × 953 CSS px, captured at 1× in the in-app browser).
- Full-view comparison: `direction-3-comparison.png`; both images opened together. Implementation was proportionally fitted into the comparison canvas, not stretched.
- State: first page, light theme, thumbnail sidebar open, full-page fit.
- Updated state: `updated-preview-light.png`, page 2 at 70%, changed cover name and shared remark.
- The available browser viewport differs from the generated target. This is a responsive direction check, not a pixel-identical certification. The prototype retains its scenario strip and sample disclaimer, reducing available paper height. Fit-page consequently displays a smaller sheet.

## Findings and iterations

1. [P2, resolved] Initial position restoration removed the top paper gutter. Restoring and navigating now subtract the same 40 px gutter. Final screenshot shows the entire cover and surrounding canvas.
2. [P2, resolved] Fixed-size thumbnails pushed the fourth page below the visible sidebar at this viewport. Thumbnail sizes now follow available reader height with a bounded minimum and maximum. Final screenshot shows all four page labels.
3. No remaining actionable P0/P1/P2 findings within the selected interaction prototype scope.

## Required fidelity surfaces

- Typography: sans-serif interface and Songti/SimSun document text retained. Toolbar and sidebar labels remain readable. Title is truncated on narrow widths rather than breaking the header.
- Spacing: white header, 244 px sidebar, 58 px toolbar, 40 px reading gutter. Paper stays in its original A4 aspect ratio. Full-page fit adapts to available height.
- Colors: white controls and sidebar, pale gray #f2f5f7 reading canvas, teal #176b63 controls and selected thumbnails. Removed dark viewer surfaces.
- Assets: document thumbnails render the same document component as the reading pane. Existing Lucide stroke icons fit the reference. No raster artwork is required.
- Copy: same cover, company name, three material categories, amounts, and shared remarks. No search control was added: search is outside this prototype's two-scenario scope. V1/V2 and sample notices remain for review clarity.
- Focused checks: cover typography/table and toolbar inspected at native screenshot resolution; updated material table and status banner inspected separately in `updated-preview-light.png`.

## Interaction verification

- Click page 2 thumbnail; enlarge from full-page scale (60%) to 70%.
- Return to drafting, apply example name and remark changes, update preview.
- Confirm restored page 2, unchanged 70% zoom, V2, updated shared remark and name.
- Use “查看封面”; switch back to full-page fit.
- Collapse and reopen sidebar; reset normal scenario.
- Browser console: no warning/error entries returned after verification.
- `npm run build`: passed from prototype directory.

## Limits and follow-up

- Four-page HTML demonstration, not a generated production PDF; no OA/backend integration or business code changes.
- Smaller/mobile viewports were not browser-tested in this iteration.
- Optional P3: final implementation can remove the prototype scenario strip to give the document more height.

## Follow-up: preview entry in terms tab

- User correction: move preview entry into 条款信息, remove it from 基本信息 and shared header.
- Evidence: `terms-preview-entry.png` at 1395 × 953. Visually checked the right-aligned terms toolbar button and two-tab navigation.
- Verified in browser: 基本信息 has zero preview buttons; applying sample edits and switching to 条款信息 reveals 更新并预览合同; generation succeeds; returning selects 条款信息 and restores its preview button. No console warnings/errors.
- Build passed. This is a scoped interaction correction; the selected light document reader remains unchanged.
- final result: passed
