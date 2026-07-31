#!/usr/bin/env node
/**
 * Dependency audit gate.
 *
 * `npm audit` has no way to accept a single advisory, so the choice it offers
 * is "fail on everything" or "lower the severity threshold". Neither is honest:
 * the first blocks on advisories that cannot affect this app, the second stops
 * reporting real ones.
 *
 * This gate fails on every advisory at or above the threshold *except* those
 * listed in audit-allowlist.json, each of which must carry a reason and a
 * review date. An exception is a decision someone made and signed, not a
 * silently raised threshold.
 *
 *   node scripts/audit-gate.mjs [--audit-level=high]
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const SEVERITY_ORDER = ['info', 'low', 'moderate', 'high', 'critical']

const levelArg = process.argv.find((arg) => arg.startsWith('--audit-level='))
const threshold = levelArg ? levelArg.split('=')[1] : 'high'
const minIndex = SEVERITY_ORDER.indexOf(threshold)
if (minIndex === -1) {
  console.error(`Unknown --audit-level=${threshold}`)
  process.exit(2)
}

/** @type {{allow: Array<{id: string, package: string, reason: string, reviewBy: string}>}} */
const allowlist = JSON.parse(readFileSync(join(here, 'audit-allowlist.json'), 'utf8'))
const allowedIds = new Set(allowlist.allow.map((entry) => entry.id))

// `npm audit` exits non-zero when it finds anything, so capture rather than throw.
let raw = ''
try {
  raw = execFileSync('npm', ['audit', '--json'], { cwd: join(here, '..'), encoding: 'utf8' })
} catch (error) {
  raw = error.stdout ?? ''
}
if (!raw.trim()) {
  console.error('npm audit produced no output')
  process.exit(2)
}

const report = JSON.parse(raw)
const blocking = []
const accepted = []

for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  if (SEVERITY_ORDER.indexOf(vuln.severity) < minIndex) continue

  for (const via of vuln.via) {
    // A string `via` means "vulnerable because a dependency is"; the advisory
    // itself is reported on that dependency, so it is counted there.
    if (typeof via === 'string') continue
    const id = via.url?.split('/').pop()
    const record = { package: vuln.name, id, title: via.title, severity: vuln.severity }
    if (id && allowedIds.has(id)) accepted.push(record)
    else blocking.push(record)
  }
}

// Flag allowlist entries that are past review, so an exception cannot quietly
// become permanent.
const today = new Date().toISOString().slice(0, 10)
const stale = allowlist.allow.filter((entry) => entry.reviewBy < today)

for (const entry of accepted) {
  console.log(`ACCEPTED  ${entry.severity.padEnd(8)} ${entry.id}  ${entry.package}`)
}
for (const entry of stale) {
  console.log(`STALE     review date ${entry.reviewBy} has passed for ${entry.id} - re-check it`)
}
for (const entry of blocking) {
  console.log(`BLOCKING  ${entry.severity.padEnd(8)} ${entry.id}  ${entry.package}: ${entry.title}`)
}

if (blocking.length > 0) {
  console.error(
    `\n${blocking.length} advisory/advisories at or above "${threshold}" are not accepted.\n` +
      'Upgrade the dependency, or add a justified entry to scripts/audit-allowlist.json.',
  )
  process.exit(1)
}

console.log(
  `\nNo unaccepted advisories at or above "${threshold}"` +
    (accepted.length ? ` (${accepted.length} accepted with documented reasons).` : '.'),
)
if (stale.length > 0) {
  console.error(`${stale.length} allowlist entry/entries are past their review date.`)
  process.exit(1)
}
