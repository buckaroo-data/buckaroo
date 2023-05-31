import * as React from 'react';
import {
  OperationViewer,
} from '../../js/components/Operations';
import {bakedOperations, bakedCommandConfig } from '../../js/components/staticData';


export default function Simple() {
    return (
        <OperationViewer
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
