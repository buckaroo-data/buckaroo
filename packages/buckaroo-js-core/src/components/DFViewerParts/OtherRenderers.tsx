import * as _ from "lodash-es";
import { ValueFormatterFunc } from "ag-grid-community";

export const getTextCellRenderer = (formatter: ValueFormatterFunc<any>) => {
    const TextCellRenderer = (props: any) => {
        return <span>{formatter(props)}</span>;
    };
    return TextCellRenderer;
};

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const buildPhrasePattern = (phrase: string | string[]): RegExp | undefined => {
    const phrases = (_.isArray(phrase) ? phrase : [phrase]).filter(
        (p) => typeof p === "string" && p.length > 0,
    );
    if (phrases.length === 0) return undefined;
    // Longest-first alternation so overlapping phrases pick the longer match.
    return new RegExp(
        `(${phrases
            .slice()
            .sort((a, b) => b.length - a.length)
            .map(escapeRegex)
            .join("|")})`,
        "gi",
    );
};

const buildRegexPattern = (source: string): RegExp | undefined => {
    if (typeof source !== "string" || source.length === 0) return undefined;
    try {
        return new RegExp(`(${source})`, "gi");
    } catch (e) {
        console.warn("buckaroo: invalid highlight_regex", source, e);
        return undefined;
    }
};

export const getHighlightTextCellRenderer = (
    formatter: ValueFormatterFunc<any>,
    spec: { phrase?: string | string[]; regex?: string },
    color: string = "yellow",
) => {
    // regex wins if both are supplied (documented as mutually exclusive).
    const pattern =
        spec.regex !== undefined
            ? buildRegexPattern(spec.regex)
            : spec.phrase !== undefined
              ? buildPhrasePattern(spec.phrase)
              : undefined;
    if (pattern === undefined) {
        return getTextCellRenderer(formatter);
    }
    const HighlightTextCellRenderer = (props: any) => {
        const raw = formatter(props);
        if (typeof raw !== "string" || raw.length === 0) {
            return <span>{raw}</span>;
        }
        const parts = raw.split(pattern);
        return (
            <span>
                {parts.map((part, i) =>
                    i % 2 === 1 ? (
                        <mark key={i} style={{ backgroundColor: color, padding: 0 }}>
                            {part}
                        </mark>
                    ) : (
                        <span key={i}>{part}</span>
                    ),
                )}
            </span>
        );
    };
    return HighlightTextCellRenderer;
};

export const LinkCellRenderer = (props: any) => {
    return <a href={props.value}>{props.value}</a>;
};

export const Base64PNGDisplayer = (props: any) => {
    const imgString = "data:image/png;base64," + props.value;
    return <img src={imgString}></img>;
};

export const SVGDisplayer = (props: any) => {
    const markup = { __html: props.value };

    return (
        <div //style={{border:'1px solid red', borderBottom:'1px solid green'}}
            dangerouslySetInnerHTML={markup}
        ></div>
    );
};
