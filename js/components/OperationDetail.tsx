import _ from 'lodash';
import {
  Operation,
  SettableArg,
  OperationEventFunc,
  NoArgEventFunc,
} from './OperationUtils';
import { ActualArg, CommandArgSpec } from './CommandUtils';
import { objWithoutNull, replaceAtIdx, replaceAtKey } from './utils';
import React from 'react';


export const OperationDetail = ({
  command,
  setCommand,
  deleteCB,
  columns,
  commandPatterns,
}: {
  command: Operation;
  setCommand: OperationEventFunc;
  deleteCB: NoArgEventFunc;
  columns: string[];
  commandPatterns: CommandArgSpec;
}) => {
  if (command === undefined) {
    return <h2> error undefined command </h2>;
  }
  const commandName = command[0]['symbol'];
  const pattern = commandPatterns[commandName];

  if (!_.isArray(pattern)) {
    //we shouldn't get here
    return <h2>unknown command {commandName}</h2>;
  } else if (_.isEqual(pattern, [null])) {
    return (
      <div className="operation-detail">
        <button onClick={deleteCB}>X</button>
      </div>
    );
  } else {
    const fullPattern = pattern as ActualArg[];
    return (
      <div className="operation-detail">
        <ArgGetters
          command={command}
          fullPattern={fullPattern}
          setCommand={setCommand}
          columns={columns}
          deleteCB={deleteCB}
        />
      </div>
    );
  }
  return <h2></h2>;
};

export const ArgGetters = ({
  command,
  fullPattern,
  setCommand,
  columns,
  deleteCB,
}: {
  command: Operation;
  fullPattern: ActualArg[];
  setCommand: OperationEventFunc;
  columns: string[];
  deleteCB: () => void;
}) => {
  const makeArgGetter = (pattern: ActualArg) => {
    const idx = pattern[0];
    const val = command[idx] as SettableArg;
    const valSetter = (newVal:unknown) => {
      const newCommand = replaceAtIdx(command, idx, newVal);
      //console.log('newCommand', newCommand);
      setCommand(newCommand as Operation);
    };
    return (
      <div key={idx}>
        <ArgGetter
          argProps={pattern}
          val={val}
          setter={valSetter}
          columns={columns}
        />
      </div>
    );
  };
  return (
    <div className="arg-getters">
      <button onClick={deleteCB}>X</button>
      {fullPattern.map(makeArgGetter)}
    </div>
  );
};

const ArgGetter = ({
  argProps,
  val,
  setter,
  columns,
}: {
  argProps: ActualArg;
  val: SettableArg;
  setter: (arg: SettableArg) => void;
  columns: string[];
}) => {
  const [_argPos, label, argType, lastArg] = argProps;

  const defaultShim = (event: { target: { value: SettableArg; }; }) => setter(event.target.value);
  if (argType === 'enum'  && _.isArray(lastArg)) {
    return (
      <fieldset>
        <label> {label} </label>
        <select defaultValue={val as string} onChange={defaultShim}>
          {lastArg.map((optionVal) => (
            <option key={optionVal} value={optionVal}>
              {optionVal}
            </option>
          ))}
        </select>
      </fieldset>
    );
  } else if (argType === 'type') {
    if (lastArg === 'integer') {
      const valSetterShim = (event: { target: { value: string; }; }) => setter(parseInt(event.target.value));
      return (
        <fieldset>
          <label> {label} </label>
          <input
            type="number"
            defaultValue={val as number}
            step="1"
            onChange={valSetterShim}
          />
        </fieldset>
      );
    } else {
      return (
        <fieldset>
          <label> {label} </label>
          <input value="dont know" />
        </fieldset>
      );
    }
  } else if (argType === 'colEnum') {
    const widgetRow = columns.map((colName: string) => {
      const colSetter = (event: { target: { value: any; }; }) => {
        const newColVal = event.target.value;
        if (_.isString(newColVal)) {
          const updatedColDict = replaceAtKey(
            val as Record<string, string>,
            colName,
            newColVal as string
          ); // as Record<string, string>
          setter(objWithoutNull(updatedColDict, ['null']));
        }
      };
      const colVal = _.get(val, colName, 'null');
      if(!_.isArray(lastArg)) {

        return <h3> arg error</h3>
      }
      return (
        <td>
          <select defaultValue={colVal} onChange={colSetter}>
            {lastArg.map((optionVal) => (
              <option key={optionVal} value={optionVal}>
                {optionVal}
              </option>
            ))}
          </select>
        </td>
      );
    });

    return (
      <div className="col-enum">
        <table>
          <thead>
            <tr>
              {columns.map((colName) => (
                <th>{colName}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>{widgetRow}</tr>
          </tbody>
        </table>
      </div>
    );
  } else {
    return <h3> unknown argtype </h3>;
  }
};
