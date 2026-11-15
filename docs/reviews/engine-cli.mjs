// scripts/ads/lib/cli.mjs — the `ad.mjs` grammar, handlers and Jose-only gate (spec §6.2, plan S3d; T10, HG-2,
// OR-1). Parsing is pure; every write goes through ledger.mjs or jobs.mjs. Output is written through
// `deps.io` only. `--execute` never reaches `joseGate` (OR-1); `reconcile` and repair-halt clearing are
// withheld in this build (CARRY-FORWARD register gates).
import { lstatSync, mkdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { SafeRunError, safeFail } from './core/errors.mjs';
import { usdArgToCents } from './money.mjs';
import { appendClearHalt, appendMedia, ledgerCheckReport, listSnapshots, maybeSnapshot, nyMonth, parseLedgerText,
  readLedgerText, reduceLedger, repairLine, repairTail, reservationSpendCents, restoreSnapshot, spendSummary, withLedgerLock } from './ledger.mjs';
import { anyAdLockHeld, createCommandBudget, joseRelease, joseSettleManual, listTakes, ownerHasLedgerEntries, planRetake, rebuildPending,
  reconcile, runPaidCall, runUnit, withAdLock } from './jobs.mjs';
import { AD_ID_RE, CAMPAIGN_RE, UNIT_RE, scopeRoot } from './paths.mjs';
import { GATES, writeApproval } from './approvals.mjs';
import { loadLocalClips, loadLocalServices, localBaseUrl, localRoute } from './providers/local-config.mjs';
import { buildLocalVideoRequest, createLocalWanPerformer, localServiceHealthy } from './providers/local-wan.mjs';
import { createLocalLtxPerformer } from './providers/local-ltx.mjs';

const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;
const LOCALTEST_OWNER_RE = /^localtest-[a-z0-9]+(?:-[a-z0-9]+)*$/u;   // S4L: dedicated local-test owner
const TAKE_RE = /^[1-9]\d*$/u;
const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/u;
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const LEDGER_ACTIONS = Object.freeze(['add-media', 'release', 'settle-manual', 'clear-halt', 'repair-tail', 'repair-line', 'check', 'restore-snapshot']);
const EXECUTE_FLAGS = Object.freeze(['execute', 'max-cost-usd']);
const COMMAND_FLAGS = Object.freeze({
  bible: EXECUTE_FLAGS,
  run: EXECUTE_FLAGS,
  rerender: EXECUTE_FLAGS,
  retake: Object.freeze([...EXECUTE_FLAGS, 'note']),
  new: Object.freeze(['campaign', 'format', 'hooks', 'protagonist']),
  approve: Object.freeze(['files', 'note']),
  status: Object.freeze([]),
  select: Object.freeze([]),
  reconcile: Object.freeze([]),
  'local-test': Object.freeze(['execute', 'max-cost-usd', 'route', 'recover']),
  ledger: Object.freeze(['month', 'add-media', 'release', 'settle-manual', 'usd', 'clear-halt', 'repair-tail', 'repair-line', 'check',
    'restore-snapshot', 'note']),
});
const POSITIONAL_COUNTS = Object.freeze({ retake: [3, 3], select: [3, 3], approve: [2, 2], reconcile: [0, 1], 'local-test': [1, 1], ledger: [0, 0] });
const BOOLEAN_FLAGS = new Set(['execute', 'repair-tail', 'recover']);
const LEDGER_COMPANIONS = Object.freeze({
  'add-media': ['note'], release: ['note'], 'settle-manual': ['usd', 'note'], 'clear-halt': ['note'], 'repair-tail': ['note'],
  'repair-line': ['note'], check: [], 'restore-snapshot': ['note'], none: ['month'],
});
const LEDGER_REQUIRED = Object.freeze({
  'add-media': ['note'], release: ['note'], 'settle-manual': ['usd', 'note'], 'clear-halt': ['note'], 'repair-tail': [],
  'repair-line': ['note'], check: [], 'restore-snapshot': ['note'], none: [],
});
const HINTS = Object.freeze({
  ad_lock_failed: 'the engine could not create ad.lock inside the owner folder. Make the owner folder a directory you own '
    + 'with mode 0700 (for example: chmod 700 <folder>), then run the command again.',
  take_state_invalid: 'the path in the details is not a valid take state or owner folder. Move it out of the runs and bible '
    + 'folders entirely (renaming it in place is not enough); keep runs/ and bible/ free of anything but real owner folders, '
    + 'never link an owner, jobs or unit folder, and run no reconcile in between. Only the first bad path is named: repeat '
    + 'until none is left.',
  submission_state_unavailable_or_invalid: "the take state file cannot be read or is invalid. Move it out of the owner's "
    + 'jobs folder (renaming it in place is not enough), then run this command again; run no reconcile in between.',
  rebuild_pending: 'these takes have ledger entries missing after a repair or restore. reconcile must rebuild them before a '
    + 'ledger_repaired halt can be cleared, and reconcile is withheld in this build.',
  ledger_unreadable: 'the ledger named in the details cannot be read for a reason other than being absent (code is the system error), '
    + 'so nothing was reported or written. Never delete, move or recreate the ledger file or its folder: they hold the spend record and '
    + 'its snapshots. Make the folder a directory you own with mode 0700 and the ledger a regular file you own with mode 0600 (for '
    + 'example: chmod 700 <folder> and chmod 600 <file>), then run the command again. If either one is a link or the wrong kind of file, '
    + 'change nothing and report the error.',
});
const USAGE = `usage: node scripts/ads/ad.mjs <command> ...
node scripts/ads/ad.mjs bible <campaign> [--execute --max-cost-usd <n>]
node scripts/ads/ad.mjs new <ad-id> --campaign <campaign> --format <pov-panic-relief|prevention-spare> --hooks <idA>,<idB> --protagonist <a|b>
node scripts/ads/ad.mjs run <ad-id> [--execute --max-cost-usd <n>]
node scripts/ads/ad.mjs retake <ad-id|campaign> <stage> <unit> [--execute --max-cost-usd <n>] [--note <text>]
node scripts/ads/ad.mjs status <ad-id>
node scripts/ads/ad.mjs select <ad-id> <shot-id> <take-number>
node scripts/ads/ad.mjs approve <ad-id|campaign> <G0|G1|G2|G3> [--files <comma-list>] [--note <text>]
node scripts/ads/ad.mjs rerender <ad-id> [--execute --max-cost-usd <n>]
node scripts/ads/ad.mjs reconcile [<ad-id>]
node scripts/ads/ad.mjs local-test <owner> [--execute --max-cost-usd 0] [--route <providerTag>] [--recover]
node scripts/ads/ad.mjs ledger [--month YYYY-MM]
node scripts/ads/ad.mjs ledger --add-media <usd> --note <text>
node scripts/ads/ad.mjs ledger --release <reserve-id> --note <text>
node scripts/ads/ad.mjs ledger --settle-manual <reserve-id> --usd <amount> --note <text>
node scripts/ads/ad.mjs ledger --clear-halt <halt-id|entryId:reason> --note <text>
node scripts/ads/ad.mjs ledger --repair-tail
node scripts/ads/ad.mjs ledger --repair-line <line-number> --note <text>
node scripts/ads/ad.mjs ledger --check [<file>]
node scripts/ads/ad.mjs ledger --restore-snapshot <snapshot-file> --note <text>
`;

/**
 * Parses the §6.2 argv grammar into `{ command, positional, flags }`. Value flags hold the typed string,
 * `--execute` and `--repair-tail` hold true, and `--check` holds true or its file.
 * @param {string[]} argv command-line words after the script name
 * @returns {{ command: string, positional: string[], flags: Record<string, string|boolean> }} the parsed command
 * @throws {SafeRunError} invalid_arguments, execute_requires_max_cost, amount_invalid, ad_id_invalid,
 *   campaign_invalid, gate_scope_invalid, take_invalid
 */
export function parseCli(argv) {
  if (!Array.isArray(argv) || argv.length === 0) safeFail('invalid_arguments');
  const [command, ...rest] = argv;
  if (typeof command !== 'string' || !Object.hasOwn(COMMAND_FLAGS, command)) safeFail('invalid_arguments');
  const allowed = COMMAND_FLAGS[command];
  const positional = [];
  const flags = {};
  for (let i = 0; i < rest.length; i += 1) {
    const token = rest[i];
    if (typeof token !== 'string') safeFail('invalid_arguments');
    if (!token.startsWith('--')) { positional.push(token); continue; }
    const name = token.slice(2);
    if (name === '' || name.includes('=') || !allowed.includes(name) || Object.hasOwn(flags, name)) safeFail('invalid_arguments');
    if (BOOLEAN_FLAGS.has(name)) { flags[name] = true; continue; }
    if (name === 'check') {
      const next = rest[i + 1];
      if (typeof next === 'string' && !next.startsWith('-')) { flags.check = next; i += 1; } else flags.check = true;
      continue;
    }
    const next = rest[i + 1];
    if (typeof next !== 'string' || next.startsWith('--')) safeFail('invalid_arguments');
    flags[name] = next;
    i += 1;
  }
  if (flags.execute === true && flags['max-cost-usd'] === undefined) safeFail('execute_requires_max_cost', { command });
  if (flags['max-cost-usd'] !== undefined) {
    // S4L: local-test accepts ONLY the exact text 0 (a 0-cent command), handled here without usdArgToCents,
    // which refuses zero itself (money.mjs). Any other value is amount_invalid. Every paid command keeps
    // the cents >= 1 floor unchanged; a positive sub-cent value must not floor into acceptance.
    if (command === 'local-test') {
      if (flags['max-cost-usd'] !== '0') safeFail('amount_invalid', { value: flags['max-cost-usd'] });
    } else {
      let cents;
      try { cents = usdArgToCents(flags['max-cost-usd'], { rounding: 'floor' }); } catch { safeFail('amount_invalid', { value: flags['max-cost-usd'] }); }
      if (!(cents >= 1)) safeFail('amount_invalid', { value: flags['max-cost-usd'] });
    }
  }
  if (flags['add-media'] !== undefined) {
    let cents;
    try { cents = usdArgToCents(flags['add-media'], { allowNegative: true }); } catch { safeFail('amount_invalid', { value: flags['add-media'] }); }
    if (cents === 0) safeFail('amount_invalid', { value: flags['add-media'] });
  }
  if (flags.usd !== undefined) {
    try { usdArgToCents(flags.usd); } catch { safeFail('amount_invalid', { value: flags.usd }); }
  }
  const [min, max] = POSITIONAL_COUNTS[command] ?? [1, 1];
  if (positional.length < min || positional.length > max) safeFail('invalid_arguments');
  assertCommandArguments(command, positional, flags);
  return { command, positional, flags };
}

/**
 * The per-command argument rules (identifiers, gate scopes, ledger action companions), run after the generic
 * position and amount checks.
 * @param {string} command command name
 * @param {string[]} positional positional words
 * @param {Record<string, string|boolean>} flags parsed flags
 * @returns {void}
 */
function assertCommandArguments(command, positional, flags) {
  if (command === 'run' || command === 'status' || command === 'rerender') {
    if (!AD_ID_RE.test(positional[0] ?? '')) safeFail('ad_id_invalid', { id: positional[0] });
  } else if (command === 'new') {
    if (!AD_ID_RE.test(positional[0] ?? '')) safeFail('ad_id_invalid', { id: positional[0] });
    assertNewArguments(flags);
  } else if (command === 'select') {
    if (!AD_ID_RE.test(positional[0] ?? '')) safeFail('ad_id_invalid', { id: positional[0] });
    if (!NAME_RE.test(positional[1] ?? '')) safeFail('invalid_arguments');
    if (!TAKE_RE.test(positional[2] ?? '')) safeFail('take_invalid', { take: positional[2] });
  } else if (command === 'reconcile') {
    if (positional.length === 1 && !AD_ID_RE.test(positional[0])) safeFail('ad_id_invalid', { id: positional[0] });
  } else if (command === 'bible') {
    if (!CAMPAIGN_RE.test(positional[0] ?? '')) safeFail('campaign_invalid', { id: positional[0] });
  } else if (command === 'local-test') {
    // S4L: a dedicated owner bible and P3 never use.
    if (!LOCALTEST_OWNER_RE.test(positional[0] ?? '')) safeFail('local_owner_invalid', { id: positional[0] });
  } else if (command === 'retake') {
    if (!AD_ID_RE.test(positional[0] ?? '') && !CAMPAIGN_RE.test(positional[0] ?? '')) safeFail('ad_id_invalid', { id: positional[0] });
    if (!NAME_RE.test(positional[1] ?? '')) safeFail('invalid_arguments');
    if (!UNIT_RE.test(positional[2] ?? '')) safeFail('invalid_arguments');
  } else if (command === 'approve') {
    assertApproveArguments(positional, flags);
  } else if (command === 'ledger') {
    assertLedgerArguments(flags);
  }
}

/**
 * The `new` flags: all four present, campaign and format valid, hooks exactly two names, protagonist a or b.
 * @param {Record<string, string|boolean>} flags parsed flags
 * @returns {void}
 */
function assertNewArguments(flags) {
  if (['campaign', 'format', 'hooks', 'protagonist'].some((name) => flags[name] === undefined)) safeFail('invalid_arguments');
  if (!CAMPAIGN_RE.test(flags.campaign)) safeFail('campaign_invalid', { id: flags.campaign });
  if (!['pov-panic-relief', 'prevention-spare'].includes(flags.format)) safeFail('invalid_arguments');
  const hooks = flags.hooks.split(',');
  if (hooks.length !== 2 || !hooks.every((h) => NAME_RE.test(h))) safeFail('invalid_arguments');
  if (!['a', 'b'].includes(flags.protagonist)) safeFail('invalid_arguments');
}

/**
 * The `approve` gate scope and `--files` rule: present exactly for G3, no empty entry.
 * @param {string[]} positional positional words
 * @param {Record<string, string|boolean>} flags parsed flags
 * @returns {void}
 */
function assertApproveArguments(positional, flags) {
  const [id, gate] = positional;
  if (!GATES.includes(gate)) safeFail('invalid_arguments');
  if (gate === 'G0') {
    if (AD_ID_RE.test(id)) safeFail('gate_scope_invalid', { id, gate });
    if (!CAMPAIGN_RE.test(id)) safeFail('campaign_invalid', { id });
  } else if (!AD_ID_RE.test(id)) {
    if (CAMPAIGN_RE.test(id)) safeFail('gate_scope_invalid', { id, gate });
    safeFail('ad_id_invalid', { id });
  }
  if (gate === 'G3') {
    if (flags.files === undefined || flags.files.split(',').some((f) => f === '')) safeFail('invalid_arguments');
  } else if (flags.files !== undefined) {
    safeFail('invalid_arguments');
  }
}

/**
 * The `ledger` rules: at most one action, its exact companions, a valid month and a positive repair line.
 * @param {Record<string, string|boolean>} flags parsed flags
 * @returns {void}
 */
function assertLedgerArguments(flags) {
  const present = LEDGER_ACTIONS.filter((action) => Object.hasOwn(flags, action));
  if (present.length > 1) safeFail('invalid_arguments');
  const action = present[0] ?? 'none';
  const allowed = LEDGER_COMPANIONS[action];
  for (const name of Object.keys(flags)) if (name !== action && !allowed.includes(name)) safeFail('invalid_arguments');
  for (const name of LEDGER_REQUIRED[action]) if (!Object.hasOwn(flags, name)) safeFail('invalid_arguments');
  if (flags.month !== undefined && !MONTH_RE.test(flags.month)) safeFail('invalid_arguments');
  if (action === 'repair-line' && !TAKE_RE.test(flags['repair-line'])) safeFail('invalid_arguments');
}

/**
 * HG-2 / §6.2: Jose-only actions need an interactive terminal and a typed confirmation. `--execute` never calls this (OR-1).
 * @param {object} deps deps carrying `io`
 * @param {{ action: string, typedId: string|number }} spec the printed action and the id Jose must type
 * @returns {Promise<void>} resolves when the typed answer matches
 * @throws {SafeRunError} interactive_terminal_required or confirmation_mismatch with `{ action }`
 */
export async function joseGate(deps, { action, typedId }) {
  if (!deps.io.isTTY) safeFail('interactive_terminal_required', { action });
  const answer = (await deps.io.prompt(`${action}\nThis is Jose's action. Type ${typedId} to confirm: `)).trim();
  if (answer !== String(typedId)) safeFail('confirmation_mismatch', { action });
}

/**
 * The action text for a Jose-only invocation, or null when the invocation is not Jose-only.
 * @param {{ command: string, positional: string[], flags: Record<string, string|boolean> }} parsed parsed CLI
 * @returns {string|null} the action text
 */
function joseActionFor(parsed) {
  if (parsed.command === 'approve') return `approve ${parsed.positional[0]} ${parsed.positional[1]}`;
  if (parsed.command !== 'ledger') return null;
  const flags = parsed.flags;
  if (Object.hasOwn(flags, 'release')) return `ledger --release ${flags.release}`;
  if (Object.hasOwn(flags, 'settle-manual')) return `ledger --settle-manual ${flags['settle-manual']}`;
  if (Object.hasOwn(flags, 'clear-halt')) return `ledger --clear-halt ${flags['clear-halt']}`;
  if (flags['repair-tail'] === true) return 'ledger --repair-tail';
  if (Object.hasOwn(flags, 'repair-line')) return `ledger --repair-line ${flags['repair-line']}`;
  if (Object.hasOwn(flags, 'restore-snapshot')) return `ledger --restore-snapshot ${flags['restore-snapshot']}`;
  if (Object.hasOwn(flags, 'add-media') && usdArgToCents(flags['add-media'], { allowNegative: true }) < 0) {
    return `ledger --add-media ${flags['add-media']}`;
  }
  return null;
}

/**
 * The success action text for a command: `ok: <action>`.
 * @param {{ command: string, positional: string[], flags: Record<string, string|boolean> }} parsed parsed CLI
 * @returns {string} the action text
 */
function actionText(parsed) {
  if (parsed.command === 'approve') return `approve ${parsed.positional[0]} ${parsed.positional[1]}`;
  if (parsed.command !== 'ledger') return parsed.command;
  const flags = parsed.flags;
  if (Object.hasOwn(flags, 'release')) return `ledger --release ${flags.release}`;
  if (Object.hasOwn(flags, 'settle-manual')) return `ledger --settle-manual ${flags['settle-manual']}`;
  if (Object.hasOwn(flags, 'clear-halt')) return `ledger --clear-halt ${flags['clear-halt']}`;
  if (flags['repair-tail'] === true) return 'ledger --repair-tail';
  if (Object.hasOwn(flags, 'repair-line')) return `ledger --repair-line ${flags['repair-line']}`;
  if (Object.hasOwn(flags, 'restore-snapshot')) return `ledger --restore-snapshot ${flags['restore-snapshot']}`;
  if (Object.hasOwn(flags, 'add-media')) return `ledger --add-media ${flags['add-media']}`;
  return 'ledger';
}

/**
 * True when a command prints only its own report (status, the ledger month report and `--check`).
 * @param {{ command: string, flags: Record<string, string|boolean> }} parsed parsed CLI
 * @returns {boolean}
 */
function isReport(parsed) {
  if (parsed.command === 'status') return true;
  if (parsed.command !== 'ledger') return false;
  return Object.hasOwn(parsed.flags, 'check') || !LEDGER_ACTIONS.some((action) => Object.hasOwn(parsed.flags, action));
}

/**
 * Reads the ledger as raw bytes with one read, and lets that read decide: `ENOENT` means the ledger file, or a
 * folder on its path, is absent, so the ledger is empty; any other failure refuses `ledger_unreadable` with the
 * ledger's repo-relative path and the system error code. No existence test is made before the read.
 * @param {object} deps deps
 * @returns {Buffer} raw ledger bytes
 * @throws {SafeRunError} ledger_unreadable when the ledger cannot be read for any reason other than being absent
 */
function readRaw(deps) {
  const ledgerPath = deps.paths.ledger.ledgerPath;
  try { return readFileSync(ledgerPath); } catch (error) {
    const code = error?.code ?? null;
    if (code === 'ENOENT') return Buffer.alloc(0);
    safeFail('ledger_unreadable', { path: path.relative(deps.paths.repoRoot, ledgerPath).split(path.sep).join('/'), code });
  }
}

/**
 * The first parsed entry whose timestamp is not a real instant, using the round-trip test.
 * @param {ReturnType<typeof parseLedgerText>} parsed parsed ledger
 * @returns {number|null} its 1-based line number, or null
 */
function tsInvalidLineNo(parsed) {
  for (const { entry, lineNo } of parsed.entries) {
    let roundTrips = false;
    try { roundTrips = new Date(entry.ts).toISOString() === entry.ts; } catch { roundTrips = false; }
    if (!roundTrips) return lineNo;
  }
  return null;
}

/**
 * Reduces a parsed ledger, mapping an unclassified throw to ledger_ts_invalid when a timestamp is not a
 * real instant (NB-2 mitigation); a SafeRunError propagates unchanged.
 * @param {ReturnType<typeof parseLedgerText>} parsed parsed ledger
 * @returns {object} the reduced state
 */
function reduceParsed(parsed) {
  try { return reduceLedger(parsed); } catch (error) {
    if (error instanceof SafeRunError) throw error;
    const lineNo = tsInvalidLineNo(parsed);
    if (lineNo !== null) safeFail('ledger_ts_invalid', { lineNo });
    throw error;
  }
}

/**
 * Reduces raw ledger bytes through the ledger_ts_invalid wrapper.
 * @param {Buffer} bytes raw ledger bytes
 * @returns {object} the reduced state
 */
function reduceRaw(bytes) { return reduceParsed(parseLedgerText(bytes.toString('utf8'))); }

/**
 * The `ledger --check` report for some text, through the same ledger_ts_invalid wrapper.
 * @param {string} text ledger text
 * @returns {object} the report
 */
function checkReport(text) {
  try { return ledgerCheckReport(text); } catch (error) {
    if (error instanceof SafeRunError) throw error;
    const lineNo = tsInvalidLineNo(parseLedgerText(text));
    if (lineNo !== null) safeFail('ledger_ts_invalid', { lineNo });
    throw error;
  }
}

/**
 * The one-line ledger status: clean, corrupt with its line and code, or torn with its line.
 * @param {object} state reduced ledger state
 * @returns {string}
 */
function ledgerLine(state) {
  if (state.status === 'corrupt') return `ledger corrupt (line ${state.corruption.lineNo}: ${state.corruption.code})`;
  if (state.status === 'torn') return `ledger torn (line ${state.tornLineNo})`;
  return 'ledger clean';
}

/**
 * One `halt <id or key> <reason>` line per open halt, or `halts none`.
 * @param {object} state reduced ledger state
 * @returns {string[]} halt lines
 */
function haltLines(state) {
  if (state.openHalts.length === 0) return ['halts none'];
  return state.openHalts.map((halt) => `halt ${halt.type === 'repair' ? halt.id : halt.key} ${halt.reason}`);
}

/**
 * Writes report lines to stdout, each followed by a newline.
 * @param {object} deps deps
 * @param {string[]} lines report lines
 * @returns {void}
 */
function printLines(deps, lines) { deps.io.stdout.write(`${lines.join('\n')}\n`); }

/**
 * Prints one failure as `error: <code>`, one JSON details line when present and the code's hint.
 * @param {object} deps deps
 * @param {unknown} error thrown value
 * @returns {void}
 */
function printError(deps, error) {
  const safe = error instanceof SafeRunError;
  const code = safe ? error.code : 'run_failed';
  deps.io.stderr.write(`error: ${code}\n`);
  if (safe && error.details !== null && error.details !== undefined) deps.io.stderr.write(`${JSON.stringify(error.details)}\n`);
  if (Object.hasOwn(HINTS, code)) deps.io.stderr.write(`hint: ${HINTS[code]}\n`);
}

/**
 * `status <ad>`: the ledger line, the ad total, per-stage and per-model totals, month totals and every open halt
 * (no cap figure since OR-5). Read-only and lockless.
 * @param {{ positional: string[] }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<number>} 0
 */
async function statusHandler(parsed, deps) {
  const adId = parsed.positional[0];
  const state = reduceRaw(readRaw(deps));
  const spend = spendSummary(state);
  const month = nyMonth(deps.now());
  const reservations = [...state.reservations.values()].filter((r) => r.scope === 'ad' && r.adId === adId);
  const stages = new Map();
  const models = new Map();
  for (const reservation of reservations) {
    const cents = reservationSpendCents(reservation);
    stages.set(reservation.entry.stage, (stages.get(reservation.entry.stage) ?? 0) + cents);
    models.set(reservation.entry.model, (models.get(reservation.entry.model) ?? 0) + cents);
  }
  const lines = [`status ${adId}`, ledgerLine(state), `ad total ${spend.byAd(adId)} cents`];
  for (const name of [...stages.keys()].sort(cmp)) lines.push(`stage ${name}: ${stages.get(name)} cents`);
  for (const name of [...models.keys()].sort(cmp)) lines.push(`model ${name}: ${models.get(name)} cents`);
  const ai = spend.monthAi(month);
  const media = spend.monthMedia(month);
  lines.push(`month ${month} ai ${ai} cents`);
  lines.push(`month ${month} ai+media ${ai + media} cents`);
  lines.push(...haltLines(state));
  printLines(deps, lines);
  return 0;
}

/**
 * `ledger` without an action: the month report. Read-only and lockless.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<number>} 0
 */
async function ledgerReport(parsed, deps) {
  const state = reduceRaw(readRaw(deps));
  const month = typeof parsed.flags.month === 'string' ? parsed.flags.month : nyMonth(deps.now());
  const spend = spendSummary(state);
  const ai = spend.monthAi(month);
  const media = spend.monthMedia(month);
  printLines(deps, [ledgerLine(state), `month ${month}`, `ai ${ai} cents`, `media ${media} cents`,
    `ai+media ${ai + media} cents`, ...haltLines(state)]);
  return 0;
}

/**
 * `ledger --check [file]`: reduces the live ledger under the ledger lock or a named file without it and
 * prints the report as JSON. Never writes.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<number>} 0
 */
async function ledgerCheck(parsed, deps) {
  let text;
  if (parsed.flags.check === true) {
    await withLedgerLock(deps.paths.ledger, { command: 'check' }, () => { text = readRaw(deps).toString('utf8'); });
  } else {
    try { text = readFileSync(path.resolve(deps.paths.ledger.root, parsed.flags.check), 'utf8'); } catch { safeFail('ledger_check_file_unavailable', { file: parsed.flags.check }); }
  }
  deps.io.stdout.write(`${JSON.stringify(checkReport(text), null, 2)}\n`);
  return 0;
}

/**
 * `ledger --add-media <usd>`: one lock hold snapshots the clean raw ledger bytes, then appends the media
 * entry, whatever its size (no cap warning since OR-5). A negative amount is Jose-only.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<{ entryId: string, cents: number, month: string }>} the appended media entry
 */
async function ledgerAddMedia(parsed, deps) {
  const text = parsed.flags['add-media'];
  const cents = usdArgToCents(text, { allowNegative: true });
  if (cents < 0) await joseGate(deps, { action: `ledger --add-media ${text}`, typedId: text });
  let entry = null;
  await withLedgerLock(deps.paths.ledger, { command: 'add-media' }, () => {
    const bytes = readRaw(deps);
    const state = reduceRaw(bytes);
    maybeSnapshot(deps.paths.ledger, bytes, state, { now: deps.now });
    entry = appendMedia(deps.paths.ledger, state, { cents, note: parsed.flags.note, now: deps.now }).entry;
  });
  return { entryId: entry.id, cents: entry.cents, month: entry.month };
}

/**
 * `ledger --release`: Jose releases an open reservation. One lock hold snapshots the clean raw bytes, then
 * `joseRelease` takes the ad (or proves quiescence) and ledger locks and appends the release.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<object>} `{ releaseId }`
 */
async function ledgerRelease(parsed, deps) {
  const reserveId = parsed.flags.release;
  await joseGate(deps, { action: `ledger --release ${reserveId}`, typedId: reserveId });
  await withLedgerLock(deps.paths.ledger, { command: 'release' }, () => {
    const bytes = readRaw(deps);
    maybeSnapshot(deps.paths.ledger, bytes, reduceRaw(bytes), { now: deps.now });
  });
  return joseRelease({ deps, reserveId, note: parsed.flags.note });
}

/**
 * `ledger --settle-manual`: Jose settles an open reservation at a typed amount. The snapshot hold is the
 * same as release; `joseSettleManual` appends the settle and any over-reservation marker.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<object>} `{ settleId, cents }`
 */
async function ledgerSettleManual(parsed, deps) {
  const reserveId = parsed.flags['settle-manual'];
  await joseGate(deps, { action: `ledger --settle-manual ${reserveId}`, typedId: reserveId });
  await withLedgerLock(deps.paths.ledger, { command: 'settle-manual' }, () => {
    const bytes = readRaw(deps);
    maybeSnapshot(deps.paths.ledger, bytes, reduceRaw(bytes), { now: deps.now });
  });
  return joseSettleManual({ deps, reserveId, usdText: parsed.flags.usd, note: parsed.flags.note });
}

/**
 * F1/N3: refuses to clear a `ledger_repaired` halt. A `rebuildPending` throw is the refusal itself, a
 * non-empty rebuild list is `rebuild_pending`, and an empty list leaves the clear withheld under F1.
 * @param {object} deps deps
 * @returns {never}
 */
function refuseRepairHaltClear(deps) {
  const pending = rebuildPending(deps);
  if (pending.length > 0) safeFail('rebuild_pending', { pending });
  safeFail('command_not_available', { command: 'ledger --clear-halt', target: 'ledger_repaired', withheldBy: ['F1'] });
}

/**
 * True when `target` names an open `ledger_repaired` halt.
 * @param {object} state reduced ledger state
 * @param {string} target clear target
 * @returns {boolean}
 */
const isOpenRepairHalt = (state, target) => state.openHalts.some((halt) => halt.type === 'repair' && halt.id === target);

/**
 * `ledger --clear-halt <target>`: derived anomaly keys are cleared normally; a `ledger_repaired` halt id is
 * withheld under F1 after the rebuild check.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<{ entryId: string, clears: string }>} the appended clear-halt
 */
async function ledgerClearHalt(parsed, deps) {
  const target = parsed.flags['clear-halt'];
  await joseGate(deps, { action: `ledger --clear-halt ${target}`, typedId: target });
  const first = reduceRaw(readRaw(deps));
  if (isOpenRepairHalt(first, target)) return refuseRepairHaltClear(deps);
  let result = null;
  await withLedgerLock(deps.paths.ledger, { command: 'clear-halt' }, () => {
    const bytes = readRaw(deps);
    const state = reduceRaw(bytes);
    if (isOpenRepairHalt(state, target)) refuseRepairHaltClear(deps);
    maybeSnapshot(deps.paths.ledger, bytes, state, { now: deps.now });
    const entry = appendClearHalt(deps.paths.ledger, state, { target, note: parsed.flags.note, now: deps.now });
    result = { entryId: entry.id, clears: entry.clears };
  });
  return result;
}

/**
 * `ledger --repair-tail`: refuses `no_torn_tail` before asking anything, then Jose confirms the torn line
 * number and one lock hold drops the torn tail. No snapshot (the ledger is not clean).
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<{ backupPath: string }>} the backup path
 */
async function ledgerRepairTail(parsed, deps) {
  const torn = parseLedgerText(readRaw(deps).toString('utf8'));
  if (!torn.torn) safeFail('no_torn_tail');
  await joseGate(deps, { action: 'ledger --repair-tail', typedId: String(torn.tornLineNo) });
  let result = null;
  await withLedgerLock(deps.paths.ledger, { command: 'repair-tail' }, () => {
    result = repairTail(deps.paths.ledger, { note: parsed.flags.note, now: deps.now });
  });
  return result;
}

/**
 * `ledger --repair-line <n>`: Jose confirms the line number and one lock hold voids that exact line.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<{ backupPath: string }>} the backup path
 */
async function ledgerRepairLine(parsed, deps) {
  const lineNo = parsed.flags['repair-line'];
  await joseGate(deps, { action: `ledger --repair-line ${lineNo}`, typedId: lineNo });
  let result = null;
  await withLedgerLock(deps.paths.ledger, { command: 'repair-line' }, () => {
    result = repairLine(deps.paths.ledger, { lineNo: Number(lineNo), note: parsed.flags.note, now: deps.now });
  });
  return result;
}

/**
 * `ledger --restore-snapshot <arg>`: NB-4 hardening. Jose confirms the file name; one lock hold refuses a
 * snapshot that is not listed, or whose snapshots folder or file is not a regular, non-empty file, then
 * restores it with the `anyAdLockHeld` wrapper. No snapshot.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<{ corruptCopyPath: string|null }>} the kept corrupt copy, if any
 */
async function ledgerRestoreSnapshot(parsed, deps) {
  const arg = parsed.flags['restore-snapshot'];
  await joseGate(deps, { action: `ledger --restore-snapshot ${arg}`, typedId: path.basename(arg) });
  let result = null;
  await withLedgerLock(deps.paths.ledger, { command: 'restore-snapshot' }, () => {
    const resolved = path.resolve(deps.paths.ledger.root, arg);
    if (!listSnapshots(deps.paths.ledger).includes(resolved)) safeFail('snapshot_not_listed', { snapshot: arg });
    let dir;
    try { dir = lstatSync(deps.paths.ledger.snapshotsDir); } catch { dir = null; }
    if (!dir || !dir.isDirectory()) safeFail('snapshot_unavailable', { snapshot: arg });
    let stat;
    try { stat = lstatSync(resolved); } catch { safeFail('snapshot_unavailable', { snapshot: arg }); }
    if (!stat.isFile() || stat.size === 0) safeFail('snapshot_unavailable', { snapshot: arg });
    result = restoreSnapshot(deps.paths.ledger, { snapshotFile: resolved, note: parsed.flags.note, now: deps.now,
      anyAdLockHeld: () => anyAdLockHeld(deps.paths) });
  });
  return result;
}

/**
 * The `ledger` handler: dispatches the one action, or prints the month report.
 * @param {{ flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<number|object>} 0 for a report, the handler result otherwise
 */
async function ledgerHandler(parsed, deps) {
  const flags = parsed.flags;
  if (Object.hasOwn(flags, 'add-media')) return ledgerAddMedia(parsed, deps);
  if (Object.hasOwn(flags, 'release')) return ledgerRelease(parsed, deps);
  if (Object.hasOwn(flags, 'settle-manual')) return ledgerSettleManual(parsed, deps);
  if (Object.hasOwn(flags, 'clear-halt')) return ledgerClearHalt(parsed, deps);
  if (flags['repair-tail'] === true) return ledgerRepairTail(parsed, deps);
  if (Object.hasOwn(flags, 'repair-line')) return ledgerRepairLine(parsed, deps);
  if (Object.hasOwn(flags, 'check')) return ledgerCheck(parsed, deps);
  if (Object.hasOwn(flags, 'restore-snapshot')) return ledgerRestoreSnapshot(parsed, deps);
  return ledgerReport(parsed, deps);
}

/**
 * `approve <id> <gate>`: Jose confirms the id, then the approval record is written. Never takes the ad lock.
 * @param {{ positional: string[], flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<{ gate: string, artifacts: number, publishable: number, acknowledged: number }>} record counts
 */
async function approveHandler(parsed, deps) {
  const [id, gate] = parsed.positional;
  await joseGate(deps, { action: `approve ${id} ${gate}`, typedId: id });
  const record = writeApproval({
    deps,
    gate,
    ...(gate === 'G0' ? { campaign: id } : { adId: id }),
    publishable: gate === 'G3' ? String(parsed.flags.files).split(',') : [],
    note: typeof parsed.flags.note === 'string' ? parsed.flags.note : null,
  });
  return { gate, artifacts: record.artifacts.length, publishable: record.publishable.length, acknowledged: record.acknowledged.length };
}

/** Refuses a command whose handler belongs to a later slice. @type {(command: string, slice: string) => () => never} */
const notYet = (command, slice) => () => safeFail('command_not_available', { command, slice });

/**
 * S4L: the local engine test stage (plan v1.3.10; OR-8). Runs the fixed clip set on ONE local route at
 * 0 cents through the existing take lifecycle, key-free, against the configured local origin. A dry run
 * (no --execute) prints the clip set and makes no call, not even /health. --recover is the local-only
 * recovery path (the general reconcile CLI stays withheld until HG-1 item 6). Jose runs the real takes
 * (HG-2); this handler never reads the key and never reaches a paid origin.
 * @param {{ positional: string[], flags: Record<string, string|boolean> }} parsed parsed CLI
 * @param {object} deps deps
 * @returns {Promise<object>} the run (or recovery) report
 */
async function localTestHandler(parsed, deps) {
  const ownerName = parsed.positional[0];
  const registry = loadLocalServices(deps.paths.creativeDir);
  const tags = Object.keys(registry.services);
  const tag = typeof parsed.flags.route === 'string' ? parsed.flags.route : tags[0];
  if (!Object.hasOwn(registry.services, tag)) safeFail('local_route_unknown', { providerTag: tag });
  const route = localRoute(registry, tag);
  const owner = { scope: 'setup', campaign: ownerName };
  const fetchImpl = typeof deps.fetch === 'function' ? deps.fetch : fetch;
  const performerFor = (t) => (t === 'local-ltx'
    ? createLocalLtxPerformer({ baseUrl: localBaseUrl(registry, t), fetchImpl })
    : createLocalWanPerformer({ baseUrl: localBaseUrl(registry, t), fetchImpl }));

  // The owner must hold only local reservations: a paid reservation under a localtest owner is refused.
  const assertLocalOwnerPure = () => {
    const ledger = reduceLedger(parseLedgerText(readLedgerText(deps.paths.ledger)));
    for (const r of ledger.reservations.values()) {
      const mine = r.scope === 'setup' && r.campaign === ownerName;
      if (mine && !Object.hasOwn(registry.services, r.providerTag)) {
        safeFail('local_owner_impure', { owner: ownerName, providerTag: r.providerTag });
      }
    }
    return ledger;
  };

  if (parsed.flags.recover === true) {
    assertLocalOwnerPure();
    const localLookups = {};
    for (const t of tags) localLookups[t] = performerFor(t);
    const paidLookups = {
      videoStatus: async () => safeFail('paid_lookup_in_local_recovery'),
      videoContent: async () => safeFail('paid_lookup_in_local_recovery'),
      generationCost: async () => safeFail('paid_lookup_in_local_recovery'),
    };
    return reconcile({ deps, owners: [owner], lookups: paidLookups, localLookups });
  }

  const { clips } = loadLocalClips(deps.paths.creativeDir);
  if (parsed.flags.execute !== true) {
    return { owner: ownerName, route: tag, execute: false,
      clips: clips.map((c) => ({ id: c.id, unit: c.unit, reserveCents: 0 })) };
  }

  // /health gates every reservation: an unreachable service refuses before any ledger or state write.
  if (!(await localServiceHealthy(localBaseUrl(registry, tag), fetchImpl))) {
    safeFail('local_service_unavailable', { providerTag: tag });
  }
  const ledger = assertLocalOwnerPure();
  // Create the owner folder under the same no-ledger-entry rule as a campaign's first bible run. A folder
  // that vanishes after money was reserved is refused by createPaidTake (owner_folder_missing), so no
  // existence test is needed here (S3d-R2 CF-1: cli.mjs decides from its own error).
  const ownerRoot = scopeRoot(deps.paths, owner);
  if (!ownerHasLedgerEntries(ledger, owner)) mkdirSync(ownerRoot, { recursive: true, mode: 0o700 });

  const command = createCommandBudget({ name: 'local-test', ceilingCents: 0, deps });
  const sha256Text = (text) => createHash('sha256').update(text, 'utf8').digest('hex');
  const results = [];
  await withAdLock(deps.paths, { ...owner, command: 'local-test' }, async () => {
    for (const clip of clips) {
      if (/^0+$/u.test(clip.still.sha256)) safeFail('local_clip_still_unset', { id: clip.id });
      // unitVersion is the pinned input fingerprint WITHOUT the seed, so a seed-change retry stays the
      // same unit version and advances the attempt (R-30's knob); requestSha256 includes the seed.
      const promptSet = clip.prompts[tag];
      const unitVersion = sha256Text(JSON.stringify({
        imageSha256: clip.still.sha256, prompt: promptSet.prompt, negativePrompt: promptSet.negativePrompt ?? '',
        width: clip.params.width, height: clip.params.height, numFrames: clip.params.numFrames, fps: clip.params.fps,
        steps: clip.params.steps, guidanceScale: clip.params.guidanceScale, model: route.model,
      }));
      const baseSeed = Number.isSafeInteger(clip.params.seed) ? clip.params.seed : 1;
      const makeTake = ({ take, attempt }) => {
        const seeded = { ...clip, params: { ...clip.params, seed: baseSeed + attempt - 1 } };
        const built = buildLocalVideoRequest({ route, clip: seeded, still: clip.still });
        return {
          scope: 'setup', campaign: ownerName, stage: 'local-test', unit: clip.unit, unitVersion,
          take, attempt, route, command,
          request: { requestSha256: built.requestSha256, inputSha256s: built.inputSha256s,
            keyframeSha256: built.keyframeSha256, localRequest: built.localRequest },
          money: built.money,
          outputPath: path.join(ownerRoot, 'outputs', clip.unit, `take-${take}.mp4`),
        };
      };
      const unit = { owner, stage: 'local-test', unit: clip.unit, unitVersion, variants: 1 };
      const performer = performerFor(tag);
      try {
        const r = await runUnit({ deps, unit, makeTake, performerFor: () => performer });
        results.push({ clip: clip.id, results: r });
      } catch (error) {
        if (error?.code !== 'retake_required') throw error;
        // Bounded retry: planRetake enforces ≤3 attempts per unit version and R-30 (the seed change makes
        // the request different). Each retry runs the planned attempt directly under the held ad lock.
        for (;;) {
          const nextAttempt = Math.max(...listTakes(deps.paths, owner, 'local-test', clip.unit)
            .filter((s) => s.unitVersion === unitVersion).map((s) => s.attempt), 0) + 1;
          const seeded = { ...clip, params: { ...clip.params, seed: baseSeed + nextAttempt - 1 } };
          const nextReq = buildLocalVideoRequest({ route, clip: seeded, still: clip.still });
          const planned = planRetake(deps.paths, { owner, stage: 'local-test', unit: clip.unit, unitVersion,
            requestSha256: nextReq.requestSha256, variants: 1 });
          const take = makeTake({ take: planned.takes[0], attempt: planned.attempt });
          try {
            const r = await runPaidCall({ deps, take, performer });
            results.push({ clip: clip.id, results: [{ take: take.take, attempt: take.attempt, outcome: 'completed', ...r }] });
            break;
          } catch (retryError) {
            if (retryError?.code === 'take_failed_retake_required' || retryError?.code === 'take_unusable_retake_required') continue;
            throw retryError;
          }
        }
      }
    }
  });
  return { owner: ownerName, route: tag, execute: true, clips: results };
}

/**
 * The command handlers; later slices replace entries (HANDLERS is a plain exported object).
 * @type {Record<string, (parsed: object, deps: object) => Promise<unknown>|unknown>}
 */
export const HANDLERS = {
  bible: notYet('bible', 'S4c'),
  retake: notYet('retake', 'S4c'),
  new: notYet('new', 'S5'),
  run: notYet('run', 'S5'),
  select: notYet('select', 'S8b'),
  rerender: notYet('rerender', 'S8b'),
  reconcile: () => safeFail('command_not_available', { command: 'reconcile', withheldBy: ['S3c containment repair', 'F1', 'F6'] }),
  'local-test': localTestHandler,
  status: statusHandler,
  approve: approveHandler,
  ledger: ledgerHandler,
};

/**
 * Runs one CLI invocation: usage (2), parse failure (2), Jose-only terminal refusal, then the handler (0) or
 * a runtime failure (1). Success prints `ok: <action>` and the JSON result except for report commands.
 * @param {string[]} argv command-line words after the script name
 * @param {object} deps deps
 * @returns {Promise<number>} exit code 0, 1 or 2
 */
export async function main(argv, deps) {
  if (!Array.isArray(argv) || argv.length === 0) {
    deps.io.stderr.write(USAGE);
    return 2;
  }
  let parsed;
  try { parsed = parseCli(argv); } catch (error) { printError(deps, error); return 2; }
  try {
    const action = joseActionFor(parsed);
    if (action !== null && !deps.io.isTTY) safeFail('interactive_terminal_required', { action });
    const result = await HANDLERS[parsed.command](parsed, deps);
    if (!isReport(parsed)) deps.io.stdout.write(`ok: ${actionText(parsed)}\n${JSON.stringify(result)}\n`);
    return 0;
  } catch (error) {
    printError(deps, error);
    return 1;
  }
}
