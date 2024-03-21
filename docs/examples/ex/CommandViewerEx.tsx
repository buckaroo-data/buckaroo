import * as React from 'react';

//import {bakedOperations, bakedCommandConfig } from '../../../js/baked_data/staticData';
import { bakedData } from 'buckaroo';
import { extraComponents } from 'buckaroo';


export default function Simple() {
    return (
        <extraComponents.OperationViewer
            operations={bakedData.bakedOperations}
            setOperations={(foo: unknown) => {
                console.log('setCommands sent', foo);
            }}
            activeColumn={'foo-column'}
            allColumns={['foo-col', 'bar-col', 'baz-col']}
            commandConfig={bakedData.bakedCommandConfig}
        />
    );
}
