import { render } from "@testing-library/react";
import { ValueFormatterParams } from "ag-grid-community";

import { getHighlightTextCellRenderer } from "./OtherRenderers";
import { getStringFormatter } from "./Displayer";

const plainFmt = getStringFormatter({ displayer: "string" });
const mkProps = (value: unknown) => ({ value } as ValueFormatterParams);

describe("string displayer highlight", () => {
    it("highlights phrase matches", () => {
        const R = getHighlightTextCellRenderer(plainFmt, { phrase: "error" });
        const { container } = render(<R {...mkProps("ERROR: load error")} />);
        const marks = Array.from(container.querySelectorAll("mark")).map(
            (m) => m.textContent,
        );
        expect(marks).toEqual(["ERROR", "error"]);
    });

    it("highlights regex matches", () => {
        const R = getHighlightTextCellRenderer(plainFmt, { regex: "\\d+" });
        const { container } = render(<R {...mkProps("err 42 / err 7")} />);
        const marks = Array.from(container.querySelectorAll("mark")).map(
            (m) => m.textContent,
        );
        expect(marks).toEqual(["42", "7"]);
    });
});
