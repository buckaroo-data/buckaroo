import { version as packageVersion } from "../package.json";

// The Release workflow runs `npm version <release>` before `pnpm run build`, so a published bundle reports the
// version it was released as. Typed explicitly so the emitted .d.ts does not import ../package.json, which is not
// shipped next to dist/.
export const version: string = packageVersion;
