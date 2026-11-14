// engine provider: the local WAN2.2 adapter (plan v1.3.10, S4L; Wan2.2 provider spec §4 REST contract).
// Rewritten from the orphan draft: the base URL comes from local-services.json (never hardcoded), the
// transport is injected (fetchImpl) so offline tests exercise the real adapter without sockets (HG-7),
// no Authorization header is ever sent, redirects are rejected, job ids are validated before URL
// construction, downloads are bounded and MP4-checked (I6), and the completed cost matches the runner's
// recordOf shape: cost { usd: 0, source: 'provider_reported' } with servedBy === providerTag (spec I8/NB-a
// as amended by v1.4.2). The performer reads state.localRequest (job-state/3); it never reads a key.
import { createHash } from 'node:crypto';
import { safeFail } from '../core/errors.mjs';
import { readBoundedVideoBody, checkMediaSignature } from '../core/download.mjs';
import { reservationFor } from '../money.mjs';
import { canonicalJson } from './llm.mjs';

const LOCAL_JOB_ID_RE = /^[A-Za-z0-9_-]+$/u;
const HEX64_RE = /^[0-9a-f]{64}$/u;
const DEFAULT_TIMEOUT_MS = 60_000;

/** @param {unknown} x @returns {boolean} */
const isObject = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
/** @param {string} text @returns {string} */
const sha256Text = (text) => createHash('sha256').update(text, 'utf8').digest('hex');

/**
 * Validates a local job id before it enters any URL (I5).
 * @param {unknown} jobId candidate id
 * @returns {string} the validated id
 * @throws {SafeRunError} local_job_id_invalid
 */
export function validateLocalJobId(jobId) {
  if (typeof jobId !== 'string' || !LOCAL_JOB_ID_RE.test(jobId)) safeFail('local_job_id_invalid', { jobId: typeof jobId === 'string' ? jobId : null });
  return jobId;
}

/**
 * Builds the pinned local request and its zero-cost money. The still is referenced by its service-side path
 * and sha256 (bytes never enter the state, T8); requestSha256 fingerprints the canonical localRequest with
 * the still replaced by its hash. money is the take runner's real input shape (worstNano/worstCents/
 * reserveCents), all zero — the serialized decimal-string worstCaseNanoUsd is produced by the reserve path.
 * @param {{ route: object, clip: object, still: { servicePath: string, sha256: string } }} call builder inputs
 * @returns {{ localRequest: object, requestSha256: string, inputSha256s: string[], keyframeSha256: string, money: { worstNano: bigint, worstCents: number, reserveCents: number } }}
 */
export function buildLocalVideoRequest({ route, clip, still }) {
  if (!isObject(route) || route.local !== true || route.kind !== 'video') safeFail('local_route_invalid');
  if (!isObject(clip) || !isObject(clip.prompts) || !isObject(clip.params)) safeFail('local_clip_invalid', { id: clip?.id ?? null });
  const promptSet = clip.prompts[route.providerTag];
  if (!isObject(promptSet) || typeof promptSet.prompt !== 'string' || promptSet.prompt.length === 0) {
    safeFail('local_clip_prompt_missing', { providerTag: route.providerTag, id: clip.id });
  }
  if (!isObject(still) || typeof still.servicePath !== 'string' || still.servicePath.length === 0 || !HEX64_RE.test(still.sha256 ?? '')) {
    safeFail('local_clip_still_invalid', { id: clip.id });
  }
  const p = clip.params;
  const localRequest = {
    prompt: promptSet.prompt,
    negativePrompt: typeof promptSet.negativePrompt === 'string' ? promptSet.negativePrompt : '',
    imagePath: still.servicePath,
    imageSha256: still.sha256,
    width: p.width,
    height: p.height,
    numFrames: p.numFrames,
    fps: p.fps,
    steps: p.steps,
    guidanceScale: p.guidanceScale,
    seed: p.seed ?? null,
    modelVariant: route.model,
  };
  const fingerprint = { ...localRequest, imagePath: `sha256:${still.sha256}` };
  return {
    localRequest,
    requestSha256: sha256Text(canonicalJson(fingerprint)),
    inputSha256s: [still.sha256],
    keyframeSha256: still.sha256,
    money: reservationFor(0n),
  };
}

/**
 * Reads a local error answer into a short stable string (no key exists on this path, so nothing to scrub).
 * @param {unknown} body parsed response body
 * @returns {string}
 */
const localErrorOf = (body) => {
  if (isObject(body) && typeof body.error === 'string' && body.error.length > 0) return body.error.slice(0, 200);
  if (isObject(body) && typeof body.detail === 'string' && body.detail.length > 0) return body.detail.slice(0, 200);
  return 'local_provider_failed';
};

/**
 * The shared local performer factory (WAN and LTX speak the same REST contract). `local: true` lets the
 * runner cross-check that the performer and the route agree on being local.
 * @param {{ baseUrl: string, providerTag: string, timeoutMs?: number, fetchImpl: typeof fetch }} call performer inputs
 * @returns {{ kind: 'async', local: true, submit: Function, poll: Function, fetchOutput: Function }}
 */
export function createLocalPerformer({ baseUrl, providerTag, timeoutMs = DEFAULT_TIMEOUT_MS, fetchImpl }) {
  if (typeof fetchImpl !== 'function') safeFail('local_transport_missing');
  const base = baseUrl.replace(/\/$/u, '');
  const call = (urlPath, init = {}) => fetchImpl(`${base}${urlPath}`, {
    redirect: 'error',
    signal: AbortSignal.timeout(timeoutMs),
    ...init,
    headers: { Accept: 'application/json', ...(init.headers ?? {}) },   // never Authorization
  });

  return {
    kind: 'async',
    local: true,
    submit: async ({ state }) => {
      const lr = state?.localRequest;
      if (!isObject(lr)) return { outcome: 'uncertain' };
      let response;
      try {
        response = await call('/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: lr.prompt,
            negative_prompt: lr.negativePrompt,
            image_path: lr.imagePath,
            image_sha256: lr.imageSha256,
            width: lr.width,
            height: lr.height,
            num_frames: lr.numFrames,
            fps: lr.fps,
            num_inference_steps: lr.steps,
            guidance_scale: lr.guidanceScale,
            seed: lr.seed,
            model_variant: lr.modelVariant,
            output_format: 'mp4',
          }),
        });
      } catch {
        return { outcome: 'uncertain' };                                  // network/timeout: no job id known
      }
      let body = null;
      try { body = await response.json(); } catch { /* non-JSON answer */ }
      if (response.status === 202 && isObject(body) && typeof body.job_id === 'string' && LOCAL_JOB_ID_RE.test(body.job_id)) {
        return { outcome: 'created', jobId: body.job_id };
      }
      // Definite rejections (bad request, missing still, validation) are provider failures; queue-full and
      // service errors stay uncertain so nothing is re-POSTed and the take can be recovered.
      if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        return { outcome: 'failed', error: localErrorOf(body) };
      }
      return { outcome: 'uncertain' };
    },
    poll: async ({ jobId }) => {
      const id = validateLocalJobId(jobId);
      let response;
      try { response = await call(`/status/${id}`); } catch { return { kind: 'poll_failure' }; }
      if (response.status === 404) return { kind: 'not_found' };
      if (!response.ok) return { kind: 'poll_failure' };
      let body;
      try { body = await response.json(); } catch { return { kind: 'poll_failure' }; }
      if (!isObject(body)) return { kind: 'poll_failure' };
      if (body.status === 'queued' || body.status === 'processing') return { kind: 'pending' };
      if (body.status === 'completed') {
        return { kind: 'completed', cost: { usd: 0, source: 'provider_reported' }, servedBy: providerTag, generationId: null };
      }
      if (body.status === 'failed') {
        return { kind: 'failed', error: localErrorOf(body), cost: null, servedBy: providerTag, generationId: null };
      }
      return { kind: 'poll_failure' };
    },
    fetchOutput: async ({ jobId }) => {
      const id = validateLocalJobId(jobId);
      let response;
      try { response = await call(`/output/${id}`, { headers: { Accept: 'video/mp4, application/octet-stream' } }); }
      catch { safeFail('video_download_failed_job_and_cost_preserved'); }
      if (!response.ok) safeFail('video_download_failed_job_and_cost_preserved');
      const bytes = await readBoundedVideoBody(response);
      if (checkMediaSignature(bytes, 'mp4') !== null) safeFail('video_download_invalid_mp4_job_and_cost_preserved');
      return bytes;
    },
  };
}

/**
 * The WAN2.2 performer.
 * @param {{ baseUrl: string, timeoutMs?: number, fetchImpl: typeof fetch }} call performer inputs
 * @returns {object} the async local performer (providerTag local-wan)
 */
export const createLocalWanPerformer = ({ baseUrl, timeoutMs, fetchImpl }) =>
  createLocalPerformer({ baseUrl, providerTag: 'local-wan', timeoutMs, fetchImpl });

/**
 * GET /health before any reservation: true only on a 2xx answer.
 * @param {string} baseUrl configured origin
 * @param {typeof fetch} fetchImpl injected transport
 * @param {number} [timeoutMs] request timeout
 * @returns {Promise<boolean>}
 */
export async function localServiceHealthy(baseUrl, fetchImpl, timeoutMs = 10_000) {
  try {
    const response = await fetchImpl(`${baseUrl.replace(/\/$/u, '')}/health`, {
      redirect: 'error',
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: 'application/json' },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** Back-compat alias for the health probe name used in the S4L contract. */
export const localWanHealthy = localServiceHealthy;
