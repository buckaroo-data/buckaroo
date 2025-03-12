import json

class TSXExample:
    """ Used to make playing with js exmaples easier.  clal these methods and get copy pastable js code to play with widget as current state is setup

    Not currently working
    """
    
    def to_dfviewer_ex(self):
        df_data_json = json.dumps(self.df_data_dict['main'], indent=4)
        summary_stats_data_json = json.dumps(self.df_data_dict['all_stats'], indent=4)
        df_config_json = json.dumps(self.df_display_args['main']['df_viewer_config'], indent=4)
        code_str = f"""
import React, {{useState}} from 'react';
import {{extraComponents}} from 'buckaroo';


export const df_data = {df_data_json}

export const summary_stats_data = {summary_stats_data_json}

export const dfv_config = {df_config_json}
        
export default function DFViewerExString() {{

    const [activeCol, setActiveCol] = useState('tripduration');
    return (
        <extraComponents.DFViewer
        df_data={{df_data}}
        df_viewer_config={{dfv_config}}
        summary_stats_data={{summary_stats_data}}
        activeCol={{activeCol}}
        setActiveCol={{setActiveCol}}
            />
    );
}}
"""
        return code_str

    def to_widgetdcfecell_ex(self):
        code_str = f"""
import React, {{useState}} from 'react';
import {{extraComponents}} from 'buckaroo';

const df_meta = {json.dumps(self.df_meta, indent=4)}

const df_display_args = {json.dumps(self.df_display_args, indent=4)}

const df_data_dict = {json.dumps(self.df_data_dict, indent=4)}

const buckaroo_options = {json.dumps(self.buckaroo_options, indent=4)}

const buckaroo_state = {json.dumps(self.buckaroo_state, indent=4)}

const command_config = {json.dumps(self.command_config, indent=4)}

const w_operations = {json.dumps(self.operations, indent=4)}

const operation_results = {json.dumps(self.operation_results, indent=4)}
        
export default function  WidgetDCFCellExample() {{
     const [bState, setBState] = React.useState<BuckarooState>(buckaroo_state);
    const [operations, setOperations] = useState<Operation[]>(w_operations);
    return (
        <extraComponents.WidgetDCFCell
            df_meta={{df_meta}}
            df_display_args={{df_display_args}}
            df_data_dict={{df_data_dict}}
            buckaroo_options={{buckaroo_options}}
            buckaroo_state={{bState}}
            on_buckaroo_state={{setBState}}
            command_config={{command_config}}
            operations={{operations}}
            on_operations={{setOperations}}
            operation_results={{operation_results}}
        />
    );
}}

"""
        return code_str
