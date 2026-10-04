/**
 * Client-side scheduler for the stats wire (rows-first c4).
 *
 * Stub: the API the tests drive, with no behaviour yet.
 */
import { BuckarooState } from "../components/WidgetTypes";
import { IModel } from "./IModel";

export type StatsModel = Pick<IModel, "get" | "on" | "off" | "send">;

export const DATAFLOW_STATE_FIELDS = ["post_processing", "cleaning_method", "quick_command_args"] as const;

export function touchesDataflow(_prev: BuckarooState | undefined, _next: BuckarooState | undefined): boolean {
    return false;
}

export interface StatsRequestOptions {
    force?: boolean;
}

export function requestStats(_model: Pick<IModel, "get" | "send">, _opts?: StatsRequestOptions): boolean {
    return false;
}

export interface OrchestratorOptions {
    model: StatsModel;
    minDebounceMs?: number;
    maxDebounceMs?: number;
    multiplier?: number;
    initialRequestMs?: number;
    firstPaintTimeoutMs?: number;
}

export class StateOrchestrator {
    constructor(_opts: OrchestratorOptions) {}

    start(): void {}

    stop(): void {}

    computeDebounce(): number {
        return 0;
    }
}
