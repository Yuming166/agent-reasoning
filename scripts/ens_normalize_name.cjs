#!/usr/bin/env node
'use strict';

// ENSIP-15 normalization is delegated to the pinned reference implementation.
const { ens_normalize } = require('@adraffy/ens-normalize');
const input = process.argv[2];
if (typeof input !== 'string' || !input) {
  console.error('expected one ENS name argument');
  process.exit(2);
}
try {
  process.stdout.write(ens_normalize(input));
} catch (error) {
  console.error(error && error.message ? error.message : String(error));
  process.exit(1);
}
