import { OperationDefaultArgs } from './OperationUtils';
import { sym } from './utils';
import { symDf, CommandConfigT, bakedArgSpecs } from './CommandUtils';

export const bakedOperationDefaults: OperationDefaultArgs = {
  dropcol: [sym('dropcol'), symDf, 'col'],
  fillna: [sym('fillna'), symDf, 'col', 8],
  resample: [sym('resample'), symDf, 'col', 'monthly', {}],
};

export const bakedCommandConfig: CommandConfigT = {
  argspecs: bakedArgSpecs,
  defaultArgs: bakedOperationDefaults,
};
