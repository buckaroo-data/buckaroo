import { version as packageVersion } from "../package.json";
import * as core from "./index";

const named = core as Record<string, unknown>;
const defaultExport = core.default as Record<string, unknown>;

describe("version", () => {
    it("is the version in package.json", () => {
        expect(named.version).toBe(packageVersion);
    });

    it("is a dotted version number", () => {
        expect(named.version).toMatch(/^\d+\.\d+\.\d+/);
    });

    it("is also on the default export", () => {
        expect(defaultExport.version).toBe(packageVersion);
    });
});
