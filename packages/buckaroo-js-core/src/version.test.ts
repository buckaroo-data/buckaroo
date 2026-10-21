import { version as packageVersion } from "../package.json";
import core, { version } from "./index";

describe("version", () => {
    it("is the version in package.json", () => {
        expect(version).toBe(packageVersion);
    });

    it("is a dotted version number", () => {
        expect(version).toMatch(/^\d+\.\d+\.\d+/);
    });

    it("is also on the default export", () => {
        expect(core.version).toBe(packageVersion);
    });
});
