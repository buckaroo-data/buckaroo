import { StatsChannel } from './StatsChannel';
import { StateOrchestrator } from './StateOrchestrator';
export declare class WebSocketModel {
    private ws;
    private pendingMsg;
    private handlers;
    private state;
    private pendingChanges;
    readonly stats: StatsChannel;
    readonly scheduler: StateOrchestrator;
    constructor(ws: WebSocket, initialState: Record<string, any>);
    send(msg: any): void;
    get(key: string): any;
    set(key: string, value: any): void;
    save_changes(): void;
    on(event: string, handler: Function): void;
    off(event: string, handler: Function): void;
    private emit;
}
