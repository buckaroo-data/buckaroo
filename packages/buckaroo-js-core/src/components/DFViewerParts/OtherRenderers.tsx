import _ from "lodash";
import { ValueFormatterFunc } from "@ag-grid-community/core";

export const getTextCellRenderer = (formatter: ValueFormatterFunc<any>) => {
    const TextCellRenderer = (props: any) => {
        return <span>{formatter(props)}</span>;
    };
    return TextCellRenderer;
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
