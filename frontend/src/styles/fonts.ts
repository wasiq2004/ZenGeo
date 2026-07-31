/**
 * Self-hosted webfonts.
 *
 * Loaded from `@fontsource/*` rather than a Google Fonts CDN link: the files are
 * served from our own origin, so there is no third-party request on first paint,
 * nothing leaks a referrer to a font host, and the strict CSP does not need a
 * `font-src`/`style-src` exception for fonts.
 *
 * Two families, kept deliberately apart (see `--font-landing` / `--font-app` in
 * index.css):
 *   Poppins    - marketing surfaces (landing page, auth screens)
 *   Open Sans  - the authenticated product (user panel, admin panel)
 *
 * Two axes of restraint, because each import is bytes on first paint:
 *
 *   Weights - only the four the UI actually uses. Each weight is a separate
 *   font file, so importing the full 100-900 range would cost real downloads.
 *
 *   Subsets - `latin` and `latin-ext` only, rather than the unsuffixed entry
 *   points, which declare every script the family ships (Devanagari for
 *   Poppins, Cyrillic and Greek for Open Sans). `unicode-range` means a browser
 *   never *downloads* a subset it has no glyphs for, so the unused ones cost no
 *   font traffic - but their @font-face blocks are still parsed CSS in the
 *   critical path. Text outside these ranges falls back to the system UI font,
 *   which is the right outcome for a user-entered business name in another
 *   script: legible immediately, rather than in-brand eventually.
 */
import '@fontsource/poppins/latin-400.css'
import '@fontsource/poppins/latin-500.css'
import '@fontsource/poppins/latin-600.css'
import '@fontsource/poppins/latin-700.css'

import '@fontsource/open-sans/latin-400.css'
import '@fontsource/open-sans/latin-500.css'
import '@fontsource/open-sans/latin-600.css'
import '@fontsource/open-sans/latin-700.css'
import '@fontsource/open-sans/latin-ext-400.css'
