/**
 * Self-hosted webfonts.
 *
 * Loaded from `@fontsource/*` rather than a Google Fonts CDN link: the files are
 * served from our own origin, so there is no third-party request on first paint,
 * nothing leaks a referrer to a font host, and the strict CSP does not need a
 * `font-src`/`style-src` exception for fonts.
 *
 * Three families, kept deliberately apart (see `--font-landing`,
 * `--font-landing-body` and `--font-app` in index.css):
 *   Plus Jakarta Sans - marketing headings, matching zenautomations.in
 *   Inter             - marketing body copy, same pairing as that site
 *   Geist Mono        - figures and technical detail on the marketing surface
 *   Open Sans         - the authenticated product (user panel, admin panel)
 *
 * The marketing pair is loaded here rather than from the Google Fonts CDN the
 * reference site uses, because our CSP is `style-src 'self' 'unsafe-inline'`
 * and `font-src 'self' data:` - a fonts.googleapis.com stylesheet would be
 * blocked outright, and the font files with it.
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
// Headings. 800 is carried because the hero and section headlines use it.
import '@fontsource/plus-jakarta-sans/latin-500.css'
import '@fontsource/plus-jakarta-sans/latin-600.css'
import '@fontsource/plus-jakarta-sans/latin-700.css'
import '@fontsource/plus-jakarta-sans/latin-800.css'

// Marketing body copy.
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'

// Figures, scores and technical labels on the marketing surface. Two weights
// only - this is for numerals and short labels, never for reading.
import '@fontsource/geist-mono/latin-400.css'
import '@fontsource/geist-mono/latin-500.css'

import '@fontsource/open-sans/latin-400.css'
import '@fontsource/open-sans/latin-500.css'
import '@fontsource/open-sans/latin-600.css'
import '@fontsource/open-sans/latin-700.css'
import '@fontsource/open-sans/latin-ext-400.css'
