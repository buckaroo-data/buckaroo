import React, {useState} from 'react';
import {BuckarooState, extraComponents } from 'buckaroo';

export default function StatusBarEx() {
    console.clear();

    const [bState, setBState] = useState<BuckarooState>({
        auto_clean: 'conservative',
        sampled: false,
        df_display: 'main',
        post_processing: 'asdf',
        show_commands: false,
        quick_command_args: {}
    });

    return (
        <div>
            <extraComponents.InfiniteEx
            />
            <pre> {JSON.stringify(bState, null, 2)}</pre>
        </div>
    );
}
