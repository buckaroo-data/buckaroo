import { DFViewerConfig } from "./DFViewerParts/DFWhole";
import { OperationViewer } from "./Operations";
import { Operation } from "./OperationUtils";
import { CommandConfigT } from "./CommandUtils";
import { DependentTabs, OperationResult } from "./DependentTabs";
import { getFieldVal } from "./DFViewerParts/gridUtils";

export type OperationSetter = (ops: Operation[]) => void;
export interface WidgetConfig {
    showCommands: boolean;
}

export function ColumnsEditor({
    df_viewer_config,
    activeColumn,
    operations,
    setOperations,
    operation_result,
    command_config,
}: {
    df_viewer_config: DFViewerConfig;
  activeColumn: [string, string];
    operations: Operation[];
    setOperations: OperationSetter;
    operation_result: OperationResult;
    command_config: CommandConfigT;
}) {
    /*
    console.log("ColumnsEditor", df_viewer_config, activeColumn, operations, 
        operation_result, command_config);
    */
  const allColumns = df_viewer_config.column_config.map(getFieldVal)
    return (
        <div className="columns-editor" style={{ width: "100%" }}>
            <div>
                <OperationViewer
                    operations={operations}
                    setOperations={setOperations}
                    activeColumn={activeColumn[1]}
                    allColumns={allColumns}
                    command_config={command_config}
                />
                <DependentTabs filledOperations={operations} 
                               operation_result={operation_result} />
            </div>
        </div>
    );
}
