import { default as React } from '../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { Operation, SetOperationsFunc } from './OperationUtils';
export interface OperationsListProps {
    operations: Operation[];
    setOperations: SetOperationsFunc;
    activeKey: string;
    setActiveKey: React.Dispatch<React.SetStateAction<string>>;
}
export declare const OperationsList2: React.FC<OperationsListProps>;
