import React, { useState } from 'react';
import {
  BuckarooState,
  extraComponents,
  BuckarooOptions,
  DFMeta,
} from 'buckaroo';

export default function StatusBarEx() {
  console.clear();
  const dfm: DFMeta = {
    columns: 5,
    rows_shown: 20,
    filtered_rows: 300_000,
    total_rows: 8_777_444,
  };

  const [bState, setBState] = useState<BuckarooState>({
    auto_clean: 'conservative',
    sampled: false,
    df_display: 'main',
    post_processing: 'asdf',
    show_commands: false,
    quick_command_args: {},
  });

  const bOptions: BuckarooOptions = {
    auto_clean: ['aggressive', 'conservative'],
    post_processing: ['', 'asdf'],
    sampled: ['random'],
    show_commands: ['on'],
    df_display: ['main'],
  };

  return (
    <div>
      <extraComponents.StatusBar
        dfMeta={dfm}
        buckarooState={bState}
        setBuckarooState={setBState}
        buckarooOptions={bOptions}
      />
      <pre> {JSON.stringify(bState, null, 2)}</pre>
    </div>
  );
}
