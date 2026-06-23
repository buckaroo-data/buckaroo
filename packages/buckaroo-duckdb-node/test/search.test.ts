import { describe, it, expect } from 'vitest';
import { buildSearchTransform, isSearchableType, isActiveSearch } from '../src/search';

describe('isSearchableType', () => {
  it.each([
    ['VARCHAR', true],
    ['TEXT', true],
    ['UUID', true],
    ['BOOLEAN', false], // folded into "string" by colType, but not text
    ['BIGINT', false],
    ['DOUBLE', false],
    ['DATE', false],
    ['VARCHAR[]', false],
  ])('%s → %s', (duckType, expected) => {
    expect(isSearchableType(duckType)).toBe(expected);
  });
});

describe('isActiveSearch', () => {
  it.each([
    ['', false],
    [null, false],
    [undefined, false],
    ['x', true],
  ])('%s → %s', (term, expected) => {
    expect(isActiveSearch(term as string)).toBe(expected);
  });
});

describe('buildSearchTransform', () => {
  it('ORs a case-sensitive contains() over every text column', () => {
    const sql = buildSearchTransform(['name', 'city'], 'Al').apply('SELECT * FROM t');
    expect(sql).toBe(
      `SELECT * FROM (SELECT * FROM t) AS _search WHERE (` +
        `contains(CAST("name" AS VARCHAR), 'Al') OR ` +
        `contains(CAST("city" AS VARCHAR), 'Al'))`,
    );
  });

  it('escapes single quotes in the term', () => {
    const sql = buildSearchTransform(['name'], "O'Brien").apply('SELECT 1');
    expect(sql).toContain("contains(CAST(\"name\" AS VARCHAR), 'O''Brien')");
  });

  it('is a no-op for an empty term', () => {
    expect(buildSearchTransform(['name'], '').apply('SELECT 1')).toBe('SELECT 1');
  });

  it('is a no-op when there are no text columns', () => {
    expect(buildSearchTransform([], 'Al').apply('SELECT 1')).toBe('SELECT 1');
  });

  it('reports its kind for the effective-query seam', () => {
    expect(buildSearchTransform(['name'], 'Al').kind).toBe('search');
  });
});
