import { useState } from "react";
import { keys, map, merge } from "lodash-es";
import { Operation, SetOperationsFunc, OperationEventFunc } from "./OperationUtils";
import { CommandConfigT } from "./CommandUtils";
import { replaceInArr } from "./utils";

import { OperationDetail } from "./OperationDetail";
import { OperationsList2 } from "./OperationsList";






export const OperationAdder = ({
    column,
    addOperationCb,
    defaultArgs,
}: {
    column: string;
    addOperationCb: any;
    defaultArgs: any;
}): JSX.Element => {
    const addOperationByName = (localOperationName: string) => {
        return () => {
            const defaultOperation = defaultArgs[localOperationName];
            addOperationCb(replaceInArr(defaultOperation, "col", column));
        };
    };

    return (
        <div className="operation-adder">
            <span className={"column-name"}> Column: {column}</span>
            <fieldset>
                {keys(defaultArgs).map((optionVal) => (
                    <button key={optionVal} onClick={addOperationByName(optionVal)}>
                        {" "}
                        {optionVal}{" "}
                    </button>
                ))}
            </fieldset>
        </div>
    );
};

export const OperationViewer = ({
    operations,
    setOperations,
    activeColumn,
    allColumns,
    command_config,
}: {
    operations: Operation[];
    setOperations: SetOperationsFunc;
    activeColumn: string;
    allColumns: string[];
    command_config: CommandConfigT;
}) => {
    const opToKey = (idx: number, op: Operation): string => {
        const name = op[0]["symbol"];
        return name + idx.toString();
    };

    const operationObjs = map(Array.from(operations.entries()), ([index, element]) => {
        const rowEl: Record<string, Operation> = {};
        rowEl[opToKey(index, element)] = element;
        return rowEl;
    });
    //why am I doing this? probably something so I gauruntee a clean dict

    const operationDict = merge({}, ...operationObjs);

    const idxObjs = map(Array.from(operations.entries()), ([index, element]) => {
        const rowEl: Record<string, number> = {};
        rowEl[opToKey(index, element)] = index;
        return rowEl;
    });
    const keyToIdx = merge({}, ...idxObjs);

    // previously was null
    const [activeKey, setActiveKey] = useState("");

    function getSetOperation(key: string): OperationEventFunc {
        return (newOperation: Operation) => {
            const index = keyToIdx[key];
            const nextOperations = operations.map((c, i) => {
                if (i === index) {
                    return newOperation;
                } else {
                    return c;
                }
            });
            console.log("about to call setOperations", key, newOperation);
            setOperations(nextOperations);
        };
    }
    const getColumns = (passedOperations: Operation[]): string[] =>
        map(Array.from(passedOperations.entries()), ([index, element]) => {
            const name = element[0]["symbol"];
            const key = name + index.toString();
	    return key;
        });
    const addOperation: OperationEventFunc = (newOperation: Operation) => {
        const newOperationArr = [...operations, newOperation];
        setOperations(newOperationArr);
        const newOperationKey = getColumns(newOperationArr)[newOperationArr.length - 1]
        if (newOperationKey !== undefined) {
            setActiveKey(newOperationKey);
        }
    };
    const { argspecs, defaultArgs } = command_config;
    return (
        <div className="operations-viewer">
            <OperationAdder
                column={activeColumn}
                addOperationCb={addOperation}
                defaultArgs={defaultArgs}
            />
            <div className="operations-box">
                <h4> Operations </h4>
                <OperationsList2
                    operations={operations}
                    activeKey={activeKey}
                    setActiveKey={setActiveKey}
                    setOperations={setOperations}
                />
            </div>
            {activeKey && (
                <OperationDetail
                    command={operationDict[activeKey]}
                    setCommand={getSetOperation(activeKey)}
                    columns={allColumns}
                    commandPatterns={argspecs}
                />
            )}
        </div>
    );
};
