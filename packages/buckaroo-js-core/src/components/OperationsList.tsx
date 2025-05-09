import React from 'react';
import { getOperationKey, Operation, SetOperationsFunc } from './OperationUtils';

export interface OperationsListProps {
    operations: Operation[];
    setOperations: SetOperationsFunc;
    activeKey:string;
    setActiveKey: React.Dispatch<React.SetStateAction<string>>;
}

export const OperationsList2: React.FC<OperationsListProps> = (
    { operations, setOperations, activeKey, setActiveKey }) => {
    const handleDeleteOperation = (index: number) => {
        const newOperations = [...operations];
        newOperations.splice(index, 1);
        setOperations(newOperations);
    };

    const handlePreserveCleaning = (index: number) => {
        const newOperations = [...operations];
        const operation = newOperations[index];
        const symbol = { ...operation[0] };
        if (symbol.meta) {
            delete symbol.meta.auto_clean;
            if (Object.keys(symbol.meta).length === 0) {
                delete symbol.meta;
            }
        }
        newOperations[index] = [symbol, ...operation.slice(1)] as Operation;
        setOperations(newOperations);
    };

    return (
        <div className="operations-list">
            {operations.map((operation, index) => {
                const currentKey = getOperationKey(operations, index);
                const isAutoClean = operation[0].meta?.auto_clean === true;
                return (<div 
                    key={index} 
                    className={`operation-item default-operation ${activeKey===currentKey ? 'active': ''} ${isAutoClean ? 'auto_clean' : ''}`}
                    onClick={()=> setActiveKey(currentKey)}
                >
                    <div className="operation-content">
                        <span className="symbol">{operation[0].symbol}</span>
                        <span className="arg">{operation[2]}</span>
                        {operation[0].meta?.clean_strategy && (
                            <span className="clean-strategy">Strategy: {operation[0].meta.clean_strategy}</span>
                        )}
                        {isAutoClean && (
                            <button
                                className="preserve-button"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handlePreserveCleaning(index);
                                }}
                                title="Preserve this cleaning operation"
                            >
                                preserve
                            </button>
                        )}
                    </div>
                    <button
                        className="delete-button"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteOperation(index);
                        }}
                    >
                        ×
                    </button>
                </div>
            )})}
        </div>);
        }
