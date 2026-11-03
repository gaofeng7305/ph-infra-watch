const test = require('node:test');
const assert = require('node:assert/strict');
const map = require('../site/assets/map-logic.js');

const projects = [
  { project_id: 'one', island_group: 'Luzon', sector: 'energy', verification_status: 'verified',
    coordinates: { lat: 14, lon: 121 }, evidence: [{ url: 'https://agency.example/1', quote_or_fact: 'coordinate source', supports_fields: ['coordinates'] }] },
  { project_id: 'two', island_group: 'Visayas', sector: 'telecommunications', verification_status: 'pending_review',
    coordinates: { lat: 10, lon: 124 }, evidence: [{ url: 'https://agency.example/2', quote_or_fact: 'coordinate source', supports_fields: ['coordinates'] }] },
  { project_id: 'three', island_group: 'Mindanao', sector: 'general', verification_status: 'needs_review',
    coordinates: { lat: 7, lon: 125 }, evidence: [{ url: 'https://agency.example/3', quote_or_fact: 'not a coordinate claim', supports_fields: ['name'] }] },
];

test('three island groups filter records and provide separate counts', () => {
  assert.deepEqual(map.GROUPS, ['Luzon', 'Visayas', 'Mindanao']);
  assert.equal(map.filterProjects(projects, { region: 'Luzon' }).length, 1);
  assert.equal(map.filterProjects(projects, { region: 'Visayas' }).length, 1);
  assert.equal(map.filterProjects(projects, { region: 'Mindanao' }).length, 1);
});

test('category and verification filters combine correctly', () => {
  assert.deepEqual(map.filterProjects(projects, { category: 'energy', status: 'verified' }).map(p => p.project_id), ['one']);
  assert.deepEqual(map.filterProjects(projects, { category: 'infrastructure' }).map(p => p.project_id), ['three']);
  assert.deepEqual(map.filterProjects(projects, { status: 'unverified' }).map(p => p.project_id), ['two', 'three']);
});

test('only coordinates with a source citation can appear as map markers', () => {
  assert.equal(map.hasReliableCoordinates(projects[0]), true);
  assert.equal(map.hasReliableCoordinates(projects[1]), true);
  assert.equal(map.hasReliableCoordinates(projects[2]), false);
  assert.equal(map.hasReliableCoordinates({ coordinates: { lat: 200, lon: 0 }, evidence: [{ url: 'https://a', quote_or_fact: 'x', supports_fields: ['coordinates'] }] }), false);
  assert.equal(map.hasReliableCoordinates({ coordinates: { lat: '', lon: 0 }, evidence: [{ url: 'https://a', quote_or_fact: 'x', supports_fields: ['coordinates'] }] }), false);
});
