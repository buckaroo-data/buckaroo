//import React from 'react';
import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { OperationsList2 } from './OperationsList';
import { symDf } from './CommandUtils';
import { Operation } from './OperationUtils';

type Meta = Record<string, any>;
const renderLegacy = (ui: any) => render(ui, { legacyRoot: true });

const makeOp = (symbol: string, arg: string, meta: Meta = {}): Operation => [
  { symbol, meta },
  symDf,
  arg
];

const getTestOperations = (): Operation[] => [
  makeOp('fillna', 'col1', { auto_clean: true, clean_strategy: 'light-int' }),
  makeOp('dropcol', 'col2'),
  makeOp('remove_outliers', 'col3', { clean_strategy: 'aggressive' }),
];

describe('OperationsList2', () => {
  let setOperations: jest.Mock, setActiveKey: jest.Mock;

  beforeEach(() => {
    setOperations = jest.fn();
    setActiveKey = jest.fn();
  });

  it('renders all operations', () => {
    renderLegacy(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={''}
        setActiveKey={setActiveKey}
      />
    );
    expect(screen.getByText('fillna')).toBeInTheDocument();
    expect(screen.getByText('dropcol')).toBeInTheDocument();
    expect(screen.getByText('remove_outliers')).toBeInTheDocument();
  });

  it('displays clean_strategy if present', () => {
    renderLegacy(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={''}
        setActiveKey={setActiveKey}
      />
    );
    expect(screen.getByText(/Strategy: light-int/)).toBeInTheDocument();
    expect(screen.getByText(/Strategy: aggressive/)).toBeInTheDocument();
  });

  it('applies auto_clean and active classes', () => {
    renderLegacy(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={'fillna0'}
        setActiveKey={setActiveKey}
      />
    );
    const items = screen.getAllByRole('button', { name: /×/ }).map(btn => btn.closest('.operation-item'));
    expect(items[0]).toHaveClass('auto_clean');
    expect(items[0]).toHaveClass('active');
    expect(items[1]).not.toHaveClass('auto_clean');
    expect(items[1]).not.toHaveClass('active');
  });

  it('calls setActiveKey when an item is clicked', () => {
    const { rerender } = renderLegacy(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={''}
        setActiveKey={setActiveKey}
      />
    );
    const item = screen.getByText('dropcol').closest('.operation-item');
    fireEvent.click(item!);
    expect(setActiveKey).toHaveBeenCalled();
    
    // Re-render with the new activeKey to verify the class is applied
    rerender(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={setActiveKey.mock.calls[0][0]}
        setActiveKey={setActiveKey}
      />
    );
    
    // Use getAllByText and filter to find the active item
    const activeItems = screen.getAllByText('dropcol')
      .map(el => el.closest('.operation-item'))
      .filter(el => el?.classList.contains('active'));
    
    expect(activeItems).toHaveLength(1);
    expect(activeItems[0]).toHaveClass('active');
  });

  it('calls setOperations when delete is clicked', () => {
    const testOperations = getTestOperations();
    renderLegacy(
      <OperationsList2
        operations={testOperations}
        setOperations={setOperations}
        activeKey={''}
        setActiveKey={setActiveKey}
      />
    );
    const deleteBtn = screen.getAllByRole('button', { name: /×/ })[0];
    fireEvent.click(deleteBtn);
    expect(setOperations).toHaveBeenCalled();
    
    // Verify the operation was actually removed
    const updatedOperations = setOperations.mock.calls[0][0];
    expect(updatedOperations).toHaveLength(testOperations.length - 1);
    expect(updatedOperations[0][0].symbol).toBe('dropcol'); // First operation should now be the second one
    expect(updatedOperations[1][0].symbol).toBe('remove_outliers'); // Second operation should now be the third one
  });

  it('calls setOperations when preserve is clicked', () => {
    renderLegacy(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={''}
        setActiveKey={setActiveKey}
      />
    );
    const preserveBtn = screen.getByRole('button', { name: /preserve/ });
    fireEvent.click(preserveBtn);
    expect(setOperations).toHaveBeenCalled();
    // Verify the operation was updated correctly
    const updatedOperations = setOperations.mock.calls[0][0];
    expect(updatedOperations[0][0].meta).not.toHaveProperty('auto_clean');
    expect(updatedOperations[0][0].meta).toHaveProperty('clean_strategy', 'light-int');

  });

  it('only shows preserve button for operations with auto_clean: true', () => {
    renderLegacy(
      <OperationsList2
        operations={getTestOperations()}
        setOperations={setOperations}
        activeKey={''}
        setActiveKey={setActiveKey}
      />
    );
    // First operation has auto_clean: true
    expect(screen.getByText('fillna').closest('.operation-item')).toHaveClass('auto_clean');
    expect(screen.getByRole('button', { name: /preserve/ })).toBeInTheDocument();
    
    // Second operation has no auto_clean
    expect(screen.getByText('dropcol').closest('.operation-item')).not.toHaveClass('auto_clean');
    expect(screen.queryAllByRole('button', { name: /preserve/ })).toHaveLength(1);
  });
});
