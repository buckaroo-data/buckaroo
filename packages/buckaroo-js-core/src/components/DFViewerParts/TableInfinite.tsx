"use strict";
import { useState } from "react";

import { winners } from "../../baked_data/olympic-winners";
import {
//    getDs,
//    getPayloadKey,
    //@ts-ignore
    PayloadArgs,
    //  sourceName,
} from "./gridUtils";
//import { InfiniteViewer } from "./InfiniteViewerImpl";
import { Operation } from "../OperationUtils";
import * as _ from "lodash-es";
import { PayloadResponse } from "./SmartRowCache";

const data: [string, Operation[]][] = [
    ["Swimming", [[{ symbol: "foo" }, { symbol: "df" }, "green"]]],
    ["Gymnastics", [[{ symbol: "bar" }, { symbol: "df" }, "green", "purple"]]],
    ["Tennis", []],
    ["Speed Skating", []],
];

const MySelect = ({
    selectedCategory,
    setSelectedCategory,
    setOperations,
}: {
    selectedCategory: string;
    setSelectedCategory: any;
    setOperations: any;
}) => {
    const handleCategoryChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        setSelectedCategory(event.target.value);
        setOperations([[{ symbol: "sport" }, { symbol: "df" }, event.target.value]]);
    };
    return (
        <div>
            <label>
                Category:
                <select value={selectedCategory} onChange={handleCategoryChange}>
                    {data.map(([category]) => (
                        <option key={category} value={category}>
                            {category}
                        </option>
                    ))}
                </select>
            </label>
        </div>
    );
};

function addSequentialIndex(list: Record<string, any>[]) {
    return _.map(list, (item, index) => ({
        ...item,
        idx: index + 1, // Adding 1 to start the index from 1
    }));
}

function addUniqueIndex(list: Record<string, any>[]) {
    return _.map(list, (item, _index) => ({
        ...item,
        agIdx: `${item.idx}-${item.sport}`,
    }));
}

function filterBySport(list: any[], sport: string): any[] {
    return _.filter(list, { sport: sport });
}

const getDataset = (sportName: string) => {
    const retVal = addUniqueIndex(addSequentialIndex(filterBySport(winners, sportName)));
    console.log("dataset retval", retVal);
    return retVal;
};

export const InfiniteWrapper = ({
    //@ts-ignore
    payloadArgs,
    //@ts-ignore
    on_payloadArgs,
    payloadResponse,
    operations,
    
}: {
    payloadArgs: PayloadArgs;
    on_payloadArgs: (pa: PayloadArgs) => void;
    payloadResponse: PayloadResponse;
    operations: Operation[];
}) => {
    console.log("here", payloadArgs,on_payloadArgs, payloadResponse, operations);
    return <h1>broken</h1>
    //    const key = getPayloadKey(payloadResponse.key);

    /*
    const ds = useMemo(() => {
        console.log("recreating ds");
        return getDs({}); //this whole thing is broken
    }, [operations]);

    src.addRows([payloadResponse.key.start, payloadResponse.key.end], payloadResponse.data);
    src.sentLength = payloadResponse.length;

    console.log(`tableinfinite 94 found ${payloadResponse.data.length} rows for `, key);
    return (
        <div>
            <pre>{JSON.stringify(operations)}</pre>

            <InfiniteViewer dataSource={ds} operations={operations} />
        </div>
    );
    */
};

export const InfiniteEx = () => {
    // this is supposed to simulate the IPYwidgets backend
    const [selectedSport, setSelectedSport] = useState<string>("Tennis");
    const initialPA: PayloadArgs = { sourceName: "paddy", start: 0, end: 100 };
    const [paState, setPaState] = useState<PayloadArgs>(initialPA);

    const paToResp = (pa: PayloadArgs): PayloadResponse => {
        // this simulates what python does

        const dataResp = getDataset(selectedSport);
        const dataSliced = dataResp.slice(pa.start, pa.end);
        console.log("infinite ex", selectedSport, dataResp, pa.start, pa.end);
        return {
            data: dataSliced,
            key: pa,
            length: dataResp.length,
        };
    };
    const [operations, setOperations] = useState<Operation[]>([
        [{ symbol: "sport" }, { symbol: "df" }, selectedSport],
    ]);

    const resp: PayloadResponse = paToResp(paState);
    return (
        <div>
            <MySelect
                selectedCategory={selectedSport}
                setSelectedCategory={setSelectedSport}
                setOperations={setOperations}
            />

            <InfiniteWrapper
                payloadArgs={paState}
                on_payloadArgs={setPaState}
                payloadResponse={resp}
                operations={operations}
            />
        </div>
    );
};
