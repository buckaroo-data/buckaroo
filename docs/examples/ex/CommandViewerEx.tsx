import * as React from 'react';

import {extraComponents} from 'buckaroo';

const sym = extraComponents.utils.sym;
const  {
  symDf,
  CommandConfigT,
    CommandArgSpec,
      bakedArgSpecs,
}  = extraComponents.CommandUtils;

export const bakedOperations: Operation[] = [
  [sym('dropcol'), symDf, 'col1'],
  [sym('fillna'), symDf, 'col2', 5],
  [sym('resample'), symDf, 'month', 'monthly', {}],
];

export const bakedOperationDefaults: OperationDefaultArgs = {
    dropcol: [sym('dropcol'), symDf, 'col'],
    fillna: [sym('fillna'), symDf, 'col', 8],
    remove_outliers: [sym('remove_outliers'), symDf, 'col', 0.02],
    search: [sym('search'), symDf, 'col', 'term'],
    resample: [sym('resample'), symDf, 'col', 'monthly', {}],
};

export const bakedCommandConfig: CommandConfigT = {
  argspecs: bakedArgSpecs,
  defaultArgs: bakedOperationDefaults,
};


export default function Simple() {
    return (
        <extraComponents.OperationViewer
            operations={bakedOperations}
            setOperations={(foo: unknown) => {
                console.log('setCommands sent', foo);
            }}
            activeColumn={'foo-column'}
            allColumns={['foo-col', 'bar-col', 'baz-col']}
            commandConfig={bakedCommandConfig}
        />
    );
}
