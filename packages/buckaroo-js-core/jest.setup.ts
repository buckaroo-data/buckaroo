import "@testing-library/jest-dom";
import { TextDecoder, TextEncoder } from 'util';

// hyparquet uses TextDecoder/TextEncoder which jsdom doesn't provide
if (typeof globalThis.TextDecoder === 'undefined') {
    (globalThis as any).TextDecoder = TextDecoder;
}
if (typeof globalThis.TextEncoder === 'undefined') {
    (globalThis as any).TextEncoder = TextEncoder;
}
