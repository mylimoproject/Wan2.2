// engine provider: the local LTX-2.5 adapter (plan v1.3.10, S4L). LTX speaks the same REST contract as the
// WAN wrapper (POST /generate, GET /status/{id}, GET /output/{id}, GET /health); the shared performer factory
// carries the transport seam, the bounded download, the id validation and the zero-cost shape. The LTX
// wrapper service on the ROG is Jose's operator task; offline tests pin this adapter to the contract.
import { createLocalPerformer, localServiceHealthy } from './local-wan.mjs';

export { buildLocalVideoRequest, validateLocalJobId } from './local-wan.mjs';

/**
 * The LTX-2.5 performer.
 * @param {{ baseUrl: string, timeoutMs?: number, fetchImpl: typeof fetch }} call performer inputs
 * @returns {object} the async local performer (providerTag local-ltx)
 */
export const createLocalLtxPerformer = ({ baseUrl, timeoutMs, fetchImpl }) =>
  createLocalPerformer({ baseUrl, providerTag: 'local-ltx', timeoutMs, fetchImpl });

/** Back-compat alias for the health probe. */
export const localLtxHealthy = localServiceHealthy;
